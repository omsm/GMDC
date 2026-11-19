| Error Code | Description |
| :-: | :- |
| ERROR@H01| I/O Controller not working. Ex: Sensor Polling issue or no read write|
| Invalid@Sensor Cut | In checkpoint it means vehicle is not validated, but sensor is cut |
| Invalid@Sensor Cut | In Uni-WB it means WB or Exit Sensor is cut, without entry sensor |




okay do one thing, forget about DISPLAY_DEBUG. I want these message to be shown in the display by hook and cook

A. I/O locked (Modbus fault, not configured, sensor read failure): ERROR@H01

B. State ≠ IDLE (WAIT_CROSSING, MANUAL_UPDATE, etc.): Is this about after all the validation is compelted, and vehicle will be exiting? If yes, then publish to display "Vehicle@Exit" if not publishing currrently, and it will be independent of DISPLAY_DEBUG

C. Empty tag list: No publish required

D. Workflow busy: No publish

E. Mobile RFID when locked / wrong state / busy: Do the above as i have asked you to do now

F. Sensor pulse while IDLE or during RFID/ANPR: 
F.i. In checkpoint is sensor cut in IDLE, then 
F.i.1. RFID API validation will not happen.
F.i.2. UI shows sensor cut in read bg
F.i.3. Display: Invalid@Sensor Cut
F.ii. In WB, 
F.ii.a. For Uni-directional:
F.ii.a.1. Entry Sensor is cut, then display will show "Move@Forward" and the current announcements, etc wil happen
F.ii.a.2. If WB or Exit Sensor is cut, without Entry Sensor, then in display show "Invalid@Sensor Cut". 
