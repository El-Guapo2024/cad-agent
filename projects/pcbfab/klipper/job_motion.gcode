; The job's motion as the fab runs it, for Klipper's batch mode (klippy.py printer.cfg -i job_motion.gcode -o out
; -d klipper.dict): every move of the stage, the lift, the flip and the focus in the job's order. Laser marks,
; dispensing and placement are the laser card's and LumenPnP's own jobs; only their positioning is here.
FAB_HOME
; side 1: drill, tile by tile under the lens
MANUAL_STEPPER STEPPER=focus_z MOVE=0
FAB_TILE I=0 J=0
FAB_TILE I=1 J=0
FAB_TILE I=2 J=0
FAB_TILE I=0 J=1
FAB_TILE I=1 J=1
FAB_TILE I=2 J=1
FAB_TILE I=0 J=2
FAB_TILE I=1 J=2
FAB_TILE I=2 J=2
FAB_TILE I=0 J=3
FAB_TILE I=1 J=3
FAB_TILE I=2 J=3
; via fill under the head, then cure (160 C, 30 min)
MANUAL_STEPPER STEPPER=stage_x MOVE=0
MANUAL_STEPPER STEPPER=stage_y MOVE=-102.5
SET_HEATER_TEMPERATURE HEATER=platen TARGET=160
SET_HEATER_TEMPERATURE HEATER=platen TARGET=0
; flip, via fill the other side
FAB_FLIP SIDE=180
; etch side 2, tiles
FAB_TILE I=0 J=0
FAB_TILE I=2 J=3
; flip back, etch side 1
FAB_FLIP SIDE=0
FAB_TILE I=0 J=0
FAB_TILE I=2 J=3
; mask: jet, cure under the lamps (the gantry moves), open the pads with the laser
SET_PIN PIN=uv_lamps VALUE=1
SET_PIN PIN=uv_lamps VALUE=0
; reflow
SET_HEATER_TEMPERATURE HEATER=platen TARGET=200
SET_HEATER_TEMPERATURE HEATER=platen TARGET=0
; a move past travel: check that this Klipper version refuses it (manual_stepper limits differ between versions)
MANUAL_STEPPER STEPPER=platen_lift MOVE=-140
