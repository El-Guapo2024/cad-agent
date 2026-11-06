"""CAM jobs recomputed by FreeCAD 26.3 (make.py, freecadcmd) and by the app's CAM (tests/test_cam_golden.py).

A case is {"parts": [brep names], "jobs": {file: JOB}, "posts": [(post, args)]}: each JOB is a job file's list as
(kind, Name, properties), replayed by cad_agent/cam_replay.py in both, then one recompute; every Path object's
commands and each post-processor's G-code are compared. The names are the ones FreeCAD's commands give in that order.
"""

DEFAULT_TC = [("ToolBit", "Endmill", {"ShapeID": "endmill"}),
              ("ToolController", "TC__5mm_Endmill", {"Tool": "Endmill"})]

POSTS = [("linuxcnc", ""), ("grbl", ""), ("generic", "")]

CASES = {
    # the fixture plate: the default tool, the model's outline, the slot, the holes, the top, tags and dogbones
    "plate_default": {
        "parts": ["plate"],
        "jobs": {"Job": [
            ("Job", "Job", {"Model": ["plate"]}),
            *DEFAULT_TC,
            ("Profile", "Profile", {}),
            ("PocketShape", "Pocket_Shape", {"Base": [("plate", ["Face17"])]}),
            ("Drilling", "Drilling", {"Base": [("plate", ["Face7", "Face8", "Face9", "Face10"])]}),
            ("MillFace", "MillFace", {"Base": [("plate", ["Face5"])]}),
            ("DressupTag", "DressupTag", {"Base": "Profile"}),
            ("DressupDogbone", "DressupDogbone", {"Base": "Pocket_Shape"}),
        ]},
        "posts": POSTS,
    },
    # a library bit with feeds, set by the task panels' values; offset clearing, pecking, a step-down
    "plate_tool": {
        "parts": ["plate"],
        "jobs": {"Job": [
            ("Job", "Job", {"Model": ["plate"], "Description": "plate, 3 mm cutter"}),
            *DEFAULT_TC,
            ("ToolBit", "_3_175mm_Endmill", {"Bit": "3.175mm_Endmill"}),
            ("ToolController", "TC__3_175mm_Endmill", {"Tool": "_3_175mm_Endmill", "HorizFeed": "600 mm/min",
                                                       "VertFeed": "200 mm/min", "SpindleSpeed": 12000.0}),
            ("Profile", "Profile", {"ToolController": "TC__3_175mm_Endmill", "StepDown": "1.5 mm",
                                    "Direction": "CCW"}),
            ("PocketShape", "Pocket_Shape", {"ToolController": "TC__3_175mm_Endmill",
                                             "Base": [("plate", ["Face17"])], "ClearingPattern": "Offset",
                                             "StepOver": 40}),
            ("Drilling", "Drilling", {"ToolController": "TC__3_175mm_Endmill",
                                      "Base": [("plate", ["Face7", "Face10"])], "PeckEnabled": True,
                                      "ExpressionEngine": {"PeckDepth": "OpToolDiameter * 0.5"}}),
            ("DressupTag", "DressupTag", {"Base": "Profile", "Width": "6 mm", "Height": "2 mm"}),
        ]},
        "posts": [("linuxcnc", "--no-show-editor --precision=4"), ("grbl", "--no-comments"), ("generic", "")],
    },
    # the block with a pocket: the shifted outline (no tie for the nearest start), the pocket, the holes, the top
    "pocket_plate": {
        "parts": ["pocket_plate"],
        "jobs": {"Job": [
            ("Job", "Job", {"Model": ["pocket_plate"]}),
            *DEFAULT_TC,
            ("Profile", "Profile", {}),
            ("PocketShape", "Pocket_Shape", {"Base": [("pocket_plate", ["Face15"])]}),
            ("MillFace", "MillFace", {"Base": [("pocket_plate", ["Face3"])]}),
            ("Drilling", "Drilling", {"Base": [("pocket_plate", ["Face7", "Face8", "Face9", "Face14"])]}),
            ("DressupTag", "DressupTag", {"Base": "Profile"}),
            ("DressupDogbone", "DressupDogbone", {"Base": "Pocket_Shape"}),
        ]},
        "posts": POSTS,
    },
    # profiles of chosen faces: the holes from inside, an outside contour climbing, extra passes
    "plate_faces": {
        "parts": ["plate"],
        "jobs": {"Job": [
            ("Job", "Job", {"Model": ["plate"]}),
            *DEFAULT_TC,
            ("Profile", "Profile", {"Base": [("plate", ["Face18"])], "Side": "Inside"}),
            ("Profile", "Profile001", {"Base": [("plate", ["Face5"])], "NumPasses": 2, "Stepover": "1 mm",
                                       "Direction": "CCW", "UseStartPoint": True,
                                       "StartPoint": (5.0, -30.0, 0.0)}),
            ("PocketShape", "Pocket_Shape", {"Base": [("plate", ["Face19"])], "ClearingPattern": "ZigZag",
                                             "Angle": 30.0}),
        ]},
        "posts": [("linuxcnc", "")],
    },

    # the ops added on 2026-11-06, one case each so that one op's failure leaves the others' answers
    "helix": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("ToolBit", "_3_175mm_Endmill", {"Bit": "3.175mm_Endmill"}),
        ("ToolController", "TC__3_175mm_Endmill", {"Tool": "_3_175mm_Endmill"}),
        ("Helix", "Helix", {"ToolController": "TC__3_175mm_Endmill", "Base": [("plate", ["Face18"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "engrave": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("ToolBit", "_60_Deg__V_Bit", {"Bit": "60degree_Vbit"}),
        ("ToolController", "TC__60_Deg__V_Bit", {"Tool": "_60_Deg__V_Bit"}),
        ("Engrave", "Engrave", {"ToolController": "TC__60_Deg__V_Bit", "Base": [("plate", ["Face5"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "slot": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("ToolBit", "_3_175mm_Endmill", {"Bit": "3.175mm_Endmill"}),
        ("ToolController", "TC__3_175mm_Endmill", {"Tool": "_3_175mm_Endmill"}),
        ("Slot", "Slot", {"ToolController": "TC__3_175mm_Endmill", "Base": [("plate", ["Face17"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "deburr": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("ToolBit", "_45_Deg__Chamfer", {"Bit": "45degree_chamfer"}),
        ("ToolController", "TC__45_Deg__Chamfer", {"Tool": "_45_Deg__Chamfer"}),
        ("Deburr", "Deburr", {"ToolController": "TC__45_Deg__Chamfer", "Base": [("plate", ["Face5"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "threadmilling": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("ToolBit", "_5mm_thread_cutter", {"Bit": "5mm-thread-cutter"}),
        ("ToolController", "TC__5mm_thread_cutter", {"Tool": "_5mm_thread_cutter"}),
        ("ThreadMilling", "ThreadMilling", {"ToolController": "TC__5mm_thread_cutter", "Base": [("plate", ["Face18"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "tapping": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("ToolBit", "M8x1_25_Tap", {"Bit": "M8x1.25_Tap"}),
        ("ToolController", "TC__M8x1_25_Tap", {"Tool": "M8x1_25_Tap"}),
        ("Tapping", "Tapping", {"ToolController": "TC__M8x1_25_Tap", "Base": [("plate", ["Face7", "Face8"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "pocket3d": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("Pocket3D", "Pocket3D", {"Base": [("plate", ["Face19"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "millfacing": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("MillFacing", "MillFacing", {}),
    ]}, "posts": [("linuxcnc", "")]},
    "adaptive": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("Adaptive", "Adaptive", {"Base": [("plate", ["Face19"])]}),
    ]}, "posts": [("linuxcnc", "")]},
    "custom_probe": {"parts": ["plate"], "jobs": {"Job": [
        ("Job", "Job", {"Model": ["plate"]}), *DEFAULT_TC,
        ("Custom", "Custom", {"Gcode": ["(start)", "G0 X0 Y0", "M0"]}),
        ("ToolBit", "Probe", {"Bit": "probe"}),
        ("ToolController", "TC__Probe", {"Tool": "Probe"}),
        ("Probe", "Probe001", {"ToolController": "TC__Probe"}),
    ]}, "posts": [("linuxcnc", "")]},
}
