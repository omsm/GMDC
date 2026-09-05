Also I want a new more thing, which will be very easier for the operator view.
Instead of showing all the divs by default, I want simple icons, conveying the divs. The divs will be visible when a button named "Flow Details will be clicked as a big popup modal with X icon to close

in the UI only
for WB just like current;y we are showing RFID / ANPR / WEIGHT
RFID:
--
Truck Number:
--
Weight: (if weighbridge)
44 T 970 kg


and below that instead if divs show


show in symbol tick (for success), Cross (for error), loading (for thattransaction happening)
RFID (icon with on top right cornor on the icon) ---- ANPR (icon) ---- WEIGHT (icon)


Weighbridge:
RFID Read  (when RFID is not read loading icon will be shown, RFID is read then tick icon will be shown, RFID read timeout/error then cross icon will be shown)


RFID Validation (APi: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag and https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag) (When RFID API will be called loading icon, status 200 response is received then tick icon will be shown, if error status non 200 then cross icon will be shown)

ANPR Read http://localhost:5001/api/detect (When ANPR API will be called loading icon, response is received and anpr_status is 1 then tick icon will be shown, if anpr_status is 0 or 2 then cross icon will be shown)

ANPR Update (api: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/status_check https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status) (This is an optional process. If above ANPR read is anpr_status is 1 then this will be skipped, else this condition will work)




VEHICLE EXIT (Boom close API) (When VEHICLE EXIT API will be called and response is received valid then tick icon will be shown, if error then cross icon will be shown)

TRUCK EXITED (When TRUCK exits with sensor cut then loading. After sensor uncuts tick)
Then after 2 seconds RESET the UI


git config --global user.email "omshree1959@gmail.com" && git config --global user.name "OSM"