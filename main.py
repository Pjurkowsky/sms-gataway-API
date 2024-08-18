from celery import Celery
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import serial

app = FastAPI()

# init it in another file, tasks should also be elsewere i think
celery = Celery(
    __name__, broker="redis://127.0.0.1:6379/0", backend="redis://127.0.0.1:6379/0"
)


class SMS(BaseModel):
    phone_number: str
    message: str


class SMSInfo(BaseModel):
    index: int
    status: str
    sender: str
    timestamp: str  # should be date but for now w/e
    message: str


def parse_sms_response(response: str) -> list[SMSInfo]:
    """Parses the response from AT+CMGL command and returns a list of dictionaries."""
    sms_list = []
    messages = response.split("+CMGL: ")[1:]

    for message in messages:
        lines = message.splitlines()
        header = lines[0].split(",")

        sms_info = SMSInfo(
            index=int(header[0].strip()),
            status=header[1].strip().replace('"', ""),
            sender=header[2].strip().replace('"', ""),
            timestamp=header[4].strip().replace('"', "")
            + header[5].strip().replace('"', ""),
            message=lines[1].strip(),
        )

        sms_list.append(sms_info)

    return sms_list


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/send-sms")
async def add_sms_to_queue(sms: SMS) -> JSONResponse:
    send_sms.delay(sms)
    return JSONResponse(content={"message": "Sms added to Q"})


@app.get("/sms")
async def get_sms(status: str = "ALL") -> list[SMSInfo]:
    with serial.Serial(
        "/dev/ttyUSB0", 9600, timeout=1
    ) as ser:  # is this always USB0, can we ensure it?
        ser.write(b"AT+CMGF=1\r")

        response = ""
        while ser.in_waiting > 0:
            response += ser.read(1).decode()

        if "ERROR" in response:
            raise Exception("Failed to set text mode.")

        ser.write(b'AT+CMGL="ALL"\r')

        response = ""
        while ser.in_waiting > 0:
            response += ser.read(1).decode()

        if "ERROR" in response:
            raise Exception("Failed to retrive SMS")

        if response.endswith("OK"):
            return []

    return parse_sms_response(response)


@celery.task
def send_sms(sms: SMS) -> None:
    with serial.Serial(
        "/dev/ttyUSB0", 9600, timeout=1
    ) as ser:  # is this always USB0, can we ensure it?
        # some delays needed propably
        ser.write(b"AT+CMGF=1\r")

        ser.write(f'AT+CMGS="{sms.phone_number}"\r'.encode())

        ser.write(f"{sms.message}\r".encode())

        ser.write(bytes([26]))

        response = ""
        while ser.in_waiting > 0:
            response += ser.read(1).decode()

        if "ERROR" in response or not response.endswith("OK"):
            raise Exception("Failed to send SMS")
