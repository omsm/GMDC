The API endpoints all values, I want to put it in checkpoint-config. When user click on finish configration, then at that time ask "Configure API-Endpoints?" When clicked on Yes, will ask for admin password. put this password static in code level "iot-app@Csmpl@123". When this password is input and submitted, then at that time show checkpoint based required API's URL and password inputs.

Mines Entry: 
1.RFID Validation
2.Anpr Validation
3.Invalid Truck Number Validation
4.Status Check in loop
5.Boom Close

Tare Weighbridge:
1.RFID Validation
2.Anpr Validation
3.Invalid Truck Number Validation
4.Status Check in loop
5.Weight Details
6.Boom Close



1. if anpr_status is 1
   a.only top photo capture
   b. top photo add with anpi response and send the ANPR API response as payload to api "invalid_truck_url": "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number" and boom close API with payload{ 
  "truck_details": "T|D2030DBE|OD14AF2721|3000|1000|0|9580308261|IP244245525162|OD05CA3273" 
} 
   d.current weight capture.
   e. call api weight_details_url: "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details" with payload{ { 
  "current_weight": "24500", 
  "truck_details": "", 
  "front_image_name": "tare_TRIP001_OD05CA3273_front.jpg", 
  "top_image_name": "tare_TRIP001_OD05CA3273_top.jpg", 
  "anpr_image_name": "anpr_TRIP001_OD05CA3273_top.jpg" 
} 
   f. call boom close API with payload{ 
  "truck_details": "" 
}
   g. Allow vehicle Exit.(Exit traffic green and boom open)
   h. reset application.(IDLE state)
2. if anpr_status is 0
    a.only top photo capture
    b.then send the ANPR API response to "invalid_truck_url": "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number".
    c. Call api in loop "update_truck_url": "/ords/gmdc_dicsm/dlms_checkpoint/status_check",payload{ 
  "vehicleNo_web": "", 
  "vehicleNo_anpr": "", 
  "rfid": "", 
  "device_ip": "" 
} 
    d. if update_truck_url response status == 200 
                   -- current weight capture.
                   -- call api weight_details_url: "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details" with payload{ { 
  "current_weight": "24500", 
  "truck_details": "", 
  "front_image_name": "tare_TRIP001_OD05CA3273_front.jpg", 
  "top_image_name": "tare_TRIP001_OD05CA3273_top.jpg", 
  "anpr_image_name": "anpr_TRIP001_OD05CA3273_top.jpg" 
} 
                   -- call boom close API with payload{ 
  "truck_details": "T|D2030DBE|OD14AF2721|3000|1000|0|9580308261|IP244245525162|OD05CA3273" 
} 
    e. Allow vehicle Exit.(Exit traffic green and boom open)
    f. reset application.(IDLE state)


3. if anpr_status is 2
   a.then send the ANPR API response to "invalid_truck_url": "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number".
   b.Exit traffic green and boom open.
   c.Application goes to idle state. 
}


Note: Take referance from mines entry.


