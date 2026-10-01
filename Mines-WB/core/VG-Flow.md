okay now lets work on Vadhghat WB integration. Below is the API documentation for the VG WB automation. Can you check the logic and let me know if you have any questions.

Also I want you to check and implement this for all the checkpoints. When ANPR is 2 case (is. ANPR ON and response 2, and ANPR is turned off from webpage), then invalid-truck-number and status_check should be called in loop just like the flow that is implemented when ANPR id enables and response 0/2

API FLow: RFID Validation -> ANPR Validation with ANPR applciatiom -> ANPR Validation -> Check status (the loop API when ANPR is 0/2 case) -> Weight captured from Digitizer -> *Then 2 cases are here
Case 1 (If weight is within tolerance): Weight details (this API will be called only when the current weight from digitizer is within tolerance i.e. between 45000 and 45000-50, no plus, only minus is allowed) -> Boom Close API (This will be called only when the Weight details api is called i.e. the digitizer weight is within tolerance)

Case 2 (If weight is outside tolerance): Weight Adjustment (this API will be called only when the current weight from digitizer is outside tolerance i.e. less than 45000 or more than 45000-50). After this API is response I want to announce the difference weight to load or unload. If weight is overweight (ex according to api DOCUMENTATION > 45000), then at first calculate the difference weight (i.e. current weight - 45000), then play the audio error_buzzer + /Users/osm/Desktop/new-IoT/Mines-WB/voice/error/g100.wav + difference weightin KG. Then only the difference weight will be announced continously till the vehicle have exited successfully after boom opens. Here dont announce Move forward
if underweight (ex according to api DOCUMENTATION < (45000-50)), then at first calculate the difference weight (i.e. (45000 - 50) - current weight), then play the audio error_buzzer + /Users/osm/Desktop/new-IoT/Mines-WB/voice/error/g101.wav + difference weightin KG. Then only the difference weight will be announced continously till the vehicle have exited successfully after boom opens. Here dont announce Move forward

Then boom open, vehicle exits and the cycle starts again from the beginning.


---------------------------------------------------------------------------------------------------
RFID Validation: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/rfid_tag 
Payload: {  "rfid": "34161fa820328ee847f17ca0",  "device_ip": "10.80.118.140"}
Response: {  "status": 200,  "process": "VADHGHAT",  "response_type": 1,  "message": "vadhghat RFID validated successfully.",  "truck_details": "V|34161fa820328ee847f17ca0|GJ12CT8178|45000|1500|50|9582209263|10.80.118.140|GJ12CT8177",  "slip_no": "9582209263",  "do_id": 2045432,  "vehicle_id": 222,  "driver_id": 101}
---------------------------------------------------------------------------------------------------
ANPR Validation with ANPR applciatiom: Keep it same as per currently happening


---------------------------------------------------------------------------------------------------
ANPR Validation: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number 
Payload: {  "vehicleNo_web": "GJ12CT8178",  "vehicleNo_anpr": "GJ12CT8177",  "rfid": "34161fa820328ee847f17ca0",  "anpr_image": "",  "front_image": "",  "matching_score": "60%",  "anpr_status": "0",  "token": "9582209263",  "device_ip": "10.80.118.140"}


Response: {  "status": 201,  "message": "Vehicle not manually updated"}


---------------------------------------------------------------------------------------------------
Check status (the loop API when ANPR is 0/2 case): https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/status_check

Payload: {  "vehicleNo_web": "GJ12CT8178",  "vehicleNo_anpr": "GJ12OT8178",  "rfid": "34161fa820328ee847f17ca0",  "device_ip": "10.80.118.140"}
Response: {  "statusCode": 201,  "vehicleStatus": 1,  "statusMessage": "Vehicle is updated manually"}



---------------------------------------------------------------------------------------------------
Weight details (this API will be called only when the current weight from digitizer is within tolerance i.e. between 45000 and 45000-50, no plus, only minus is allowed): https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/vadhghat_weight_details
Payload: {  "current_weight": "1810",  "truck_details": "V|34161fa820328ee847f17ca0|GJ12CT8178|45000|2500|50|9582209263|10.10.180.12",  "front_image_name": "vadhghat_front_001.jpg",  "top_image_name": "vadhghat_top_001.jpg",  "anpr_image_name": "vadhghat_anpr_001.jpg"}

Response: {  "status": 200,  "response_type": 1,  "message": "Vadhghat weight details submitted successfully.",  "movement_id": 1721,  "weighment_id": 1130}




---------------------------------------------------------------------------------------------------
Weight Adjustment (this API will be called only when the current weight from digitizer is outside tolerance i.e. less than 45000 or more than 45000-50): https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment 
Payload: {  "device_ip": "10.10.180.12",  "truck_details": "V|E28068940000503F548F04BA|OD14P7339|45000|24500|50|9580109261|10.10.180.12",  "weight": 44990,  "weight_type": "o/u"}
Response: {  "status": 200,  "response_type": 1,  "message": "Vadhghat weight adjustment processed successfully. Current Vadhghat cycle has been reset. Please read the RFID card again.",  "device_ip": "10.10.180.12",  "truck_details": "V|E28068940000503F548F04BA|OD14P7339|45000|24500|50|9580109261|10.10.180.12",  "rfid_no": "E28068940000503F548F04BA",  "vehicle_no": "OD14P7339",  "token": "9580109261",  "weight": 44990,  "weight_type": "o/u",  "location_id": 163,  "location_name": "Vadhghat Weighbridge",  "reset_count": {    "entry_log": 4,    "movement": 1,    "weighment": 0,    "anpr": 1  }}




---------------------------------------------------------------------------------------------------
Boom Close API (This will be called only when the Weight details api is called i.e. the digitizer weight is within tolerance): https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/vadhghat_boom_close 
Payload: {  "truck_details": "V|34161fa820328ee847f17ca0|GJ12CT8178|45000|2500|50|9582209263|10.10.180.12"}
Response: {  "status": 200,  "message": "Vadhghat Boom Close completed successfully."}