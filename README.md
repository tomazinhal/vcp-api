# Virtual OCPP Charge Point

Use FastAPI to control messages that can be sent and handled.
An abstraction of a charger is useful to control the payload of OCPP
messages.

## Concept
The idea of this project is to showcase how a decoupled abstraction and the means
to communicate with another entity improve control of a charge point emulator.

The main idea is that messages exchanged go through 2 gates before being sent and after being received.

### Message flow from Backend to EVSE
1. Message is received.
2. Message is passed to Handler to validate payload.
3. Message is passed to Abstraction for validation.
4. Response data is received from Abstraction.
5. Response payload is created from Handler.
6. Response is sent.

### Message flow from EVSE to Backend
1. Message to be sent is requested.
2. Abstraction returns data required to create message.
3. Handler creates payload from Abstraction's data.
4. Message is sent
5. Response is received.
6. Response is validated through Handler.
7. Response is passed to Abstraction for validation and parsing.
8. Further actions can be queued.

### Abstraction 
TODO

### Handler
Makes sure that payloads are valid OCPP messages and handles that responses
are also valid OCPP messages.


# Run the code
Install the requirements.
```sh
$ pip install -r requirements.py
```

Run the example backend
```sh
$ python ws-backend.py
```

Run the emulator
```sh
$ cd evse
$ uvicorn main.evse --reload
```

## Setting up the charger
First thing that must be done before connecting to anything is configuring the 
charger. Attributes such as charger id and number of connectors can be setup here. 
But other attributes can be added, for example, capability of connectors and starting
state (i.e.: Faulted, etc...).

## Connecting to backend
Connect to the backend of choice.

## Send messages
TODO


# TODO
Add more endpoints to control abstraction. For example:
* Configure current consumption, which is useful to change subsequent MeterValues

Add more routes to abstraction and handler. For example:
* Changing transaction status depending whether Authorize or StartTransaction were
accepted or not.
