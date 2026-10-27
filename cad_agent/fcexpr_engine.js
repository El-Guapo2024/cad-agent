/* SPDX-License-Identifier: LGPL-2.1-or-later
* ui/src/expr.ts and what it uses, with ui/scripts/expr-server-entry.ts, bundled by ui/scripts/fcexprjs.py for cad_agent/fcexpr.py.
* It follows FreeCAD main 3160daf1e2b6 (LGPL-2.0-or-later and LGPL-2.1-or-later); ui/NOTICE names the files and their authors. */
// sources: 393465d34a2b830194f3beb130926c1ee5a8c9e8407798f37c3d140ea02d3730
(function() {
	//#region src/units-data.ts
	/** Each token the quantity lexer knows: its value in internal units and its dimensions. */
	var UNITS = {
		"nm": [1e-6, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"um": [.001, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"µm": [.001, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"mm": [1, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"cm": [10, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"dm": [100, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"m": [1e3, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"km": [1e6, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"l": [1e6, [
			3,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"ml": [1e3, [
			3,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"Hz": [1, [
			0,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		"kHz": [1e3, [
			0,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		"MHz": [1e6, [
			0,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		"GHz": [1e9, [
			0,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		"THz": [0xe8d4a51000, [
			0,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		"ug": [1e-9, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"µg": [1e-9, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"mg": [1e-6, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"g": [.001, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"kg": [1, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"t": [1e3, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"s": [1, [
			0,
			0,
			1,
			0,
			0,
			0,
			0,
			0
		]],
		"min": [60, [
			0,
			0,
			1,
			0,
			0,
			0,
			0,
			0
		]],
		"h": [3600, [
			0,
			0,
			1,
			0,
			0,
			0,
			0,
			0
		]],
		"A": [1, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"nA": [1e-9, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"uA": [1e-6, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"µA": [1e-6, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"mA": [.001, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"kA": [1e3, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"MA": [1e6, [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		"K": [1, [
			0,
			0,
			0,
			0,
			1,
			0,
			0,
			0
		]],
		"mK": [.001, [
			0,
			0,
			0,
			0,
			1,
			0,
			0,
			0
		]],
		"µK": [1e-6, [
			0,
			0,
			0,
			0,
			1,
			0,
			0,
			0
		]],
		"uK": [1e-6, [
			0,
			0,
			0,
			0,
			1,
			0,
			0,
			0
		]],
		"mol": [1, [
			0,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		"nmol": [1e-9, [
			0,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		"umol": [1e-6, [
			0,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		"µmol": [1e-6, [
			0,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		"mmol": [.001, [
			0,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		"cd": [1, [
			0,
			0,
			0,
			0,
			0,
			0,
			1,
			0
		]],
		"in": [25.4, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"\"": [25.4, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"ft": [304.79999999999995, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"'": [304.79999999999995, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"thou": [.0254, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"mil": [.0254, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"yd": [914.3999999999999, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"mi": [1609343.9999999998, [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"mph": [447.03999999999996, [
			1,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		"sqft": [92903.03999999998, [
			2,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"cft": [28316846.59199999, [
			3,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"lb": [.45359237, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"lbm": [.45359237, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"oz": [.028349523125, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"st": [6.35029318, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"cwt": [50.80234544, [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		"lbf": [4448.2216152605, [
			1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"N": [1e3, [
			1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"mN": [1, [
			1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"kN": [1e6, [
			1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"MN": [1e9, [
			1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"Pa": [.001, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"kPa": [1, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"MPa": [1e3, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"GPa": [1e6, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"bar": [100, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"mbar": [.1, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"Torr": [.13332236842105263, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"mTorr": [.00013332236842105263, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"uTorr": [1.3332236842105263e-7, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"µTorr": [1.3332236842105263e-7, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"psi": [6.894757293168361, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"ksi": [6894.757293168361, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"Mpsi": [6894757.293168361, [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"W": [1e6, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"nW": [.001, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"uW": [1, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"µW": [1, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"mW": [1e3, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"kW": [1e9, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"VA": [1e6, [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		"V": [1e6, [
			2,
			1,
			-3,
			-1,
			0,
			0,
			0,
			0
		]],
		"kV": [1e9, [
			2,
			1,
			-3,
			-1,
			0,
			0,
			0,
			0
		]],
		"mV": [1e3, [
			2,
			1,
			-3,
			-1,
			0,
			0,
			0,
			0
		]],
		"MS": [1, [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		"kS": [.001, [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		"S": [1e-6, [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		"mS": [1e-9, [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		"µS": [1e-12, [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		"uS": [1e-12, [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		"Ohm": [1e6, [
			2,
			1,
			-3,
			-2,
			0,
			0,
			0,
			0
		]],
		"kOhm": [1e9, [
			2,
			1,
			-3,
			-2,
			0,
			0,
			0,
			0
		]],
		"MOhm": [0xe8d4a51000, [
			2,
			1,
			-3,
			-2,
			0,
			0,
			0,
			0
		]],
		"C": [1, [
			0,
			0,
			1,
			1,
			0,
			0,
			0,
			0
		]],
		"T": [1, [
			0,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		"mT": [.001, [
			0,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		"G": [1e-4, [
			0,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		"Wb": [1e6, [
			2,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		"F": [1e-6, [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		"mF": [1e-9, [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		"µF": [1e-12, [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		"uF": [1e-12, [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		"nF": [1e-15, [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		"pF": [1e-18, [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		"H": [1e6, [
			2,
			1,
			-2,
			-2,
			0,
			0,
			0,
			0
		]],
		"mH": [1e3, [
			2,
			1,
			-2,
			-2,
			0,
			0,
			0,
			0
		]],
		"µH": [1, [
			2,
			1,
			-2,
			-2,
			0,
			0,
			0,
			0
		]],
		"uH": [1, [
			2,
			1,
			-2,
			-2,
			0,
			0,
			0,
			0
		]],
		"nH": [.001, [
			2,
			1,
			-2,
			-2,
			0,
			0,
			0,
			0
		]],
		"J": [1e6, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"mJ": [1e3, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"kJ": [1e9, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"Nm": [1e6, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"Nmm": [1e3, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"VAs": [1e6, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"CV": [1e6, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"Ws": [1e6, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"kWh": [36e11, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"eV": [1602176634e-22, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"keV": [1602176634e-19, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"MeV": [1.602176634e-7, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"cal": [4186800, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"kcal": [41868e5, [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		"°": [1, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"deg": [1, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"rad": [57.29577951308232, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"gon": [.9, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"M": [.016666666666666666, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"′": [.016666666666666666, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"AS": [.0002777777777777778, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		"″": [.0002777777777777778, [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]]
	};
	/** Unit::getTypeString: the named quantity types, first match wins. */
	var UNIT_TYPES = [
		["1", [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["Length", [
			1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["Mass", [
			0,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["TimeSpan", [
			0,
			0,
			1,
			0,
			0,
			0,
			0,
			0
		]],
		["ElectricCurrent", [
			0,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		["Temperature", [
			0,
			0,
			0,
			0,
			1,
			0,
			0,
			0
		]],
		["AmountOfSubstance", [
			0,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		["LuminousIntensity", [
			0,
			0,
			0,
			0,
			0,
			0,
			1,
			0
		]],
		["Angle", [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		["Acceleration", [
			1,
			0,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["AngleOfFriction", [
			0,
			0,
			0,
			0,
			0,
			0,
			0,
			1
		]],
		["Area", [
			2,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["CurrentDensity", [
			-2,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		["Density", [
			-3,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["DissipationRate", [
			2,
			0,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		["DynamicViscosity", [
			-1,
			1,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		["ElectricalCapacitance", [
			-2,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		["ElectricalConductance", [
			-2,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		["ElectricalConductivity", [
			-3,
			-1,
			3,
			2,
			0,
			0,
			0,
			0
		]],
		["ElectricalInductance", [
			2,
			1,
			-2,
			-2,
			0,
			0,
			0,
			0
		]],
		["ElectricalResistance", [
			2,
			1,
			-3,
			-2,
			0,
			0,
			0,
			0
		]],
		["ElectricCharge", [
			0,
			0,
			1,
			1,
			0,
			0,
			0,
			0
		]],
		["ElectricPotential", [
			2,
			1,
			-3,
			-1,
			0,
			0,
			0,
			0
		]],
		["ElectromagneticPotential", [
			1,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		["Force", [
			1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["Frequency", [
			0,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		["HeatFlux", [
			0,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		["MassMomentOfInertia", [
			2,
			1,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["AreaMomentOfInertia", [
			4,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["InverseArea", [
			-2,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["InverseLength", [
			-1,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["InverseVolume", [
			-3,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["KinematicViscosity", [
			2,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		["MagneticFieldStrength", [
			-1,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		["MagneticFlux", [
			2,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		["MagneticFluxDensity", [
			0,
			1,
			-2,
			-1,
			0,
			0,
			0,
			0
		]],
		["Magnetization", [
			-1,
			0,
			0,
			1,
			0,
			0,
			0,
			0
		]],
		["Moment", [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["Pressure", [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["Power", [
			2,
			1,
			-3,
			0,
			0,
			0,
			0,
			0
		]],
		["ShearModulus", [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["SpecificEnergy", [
			2,
			0,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["SpecificHeat", [
			2,
			0,
			-2,
			0,
			-1,
			0,
			0,
			0
		]],
		["Stiffness", [
			0,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["StiffnessDensity", [
			-2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["Stress", [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["SurfaceChargeDensity", [
			-2,
			0,
			1,
			1,
			0,
			0,
			0,
			0
		]],
		["ThermalConductivity", [
			1,
			1,
			-3,
			0,
			-1,
			0,
			0,
			0
		]],
		["ThermalExpansionCoefficient", [
			0,
			0,
			0,
			0,
			-1,
			0,
			0,
			0
		]],
		["ThermalTransferCoefficient", [
			0,
			1,
			-3,
			0,
			-1,
			0,
			0,
			0
		]],
		["UltimateTensileStrength", [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["VacuumPermittivity", [
			-3,
			-1,
			4,
			2,
			0,
			0,
			0,
			0
		]],
		["Velocity", [
			1,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		["Volume", [
			3,
			0,
			0,
			0,
			0,
			0,
			0,
			0
		]],
		["Concentration", [
			-3,
			0,
			0,
			0,
			0,
			1,
			0,
			0
		]],
		["VolumeChargeDensity", [
			-3,
			0,
			1,
			1,
			0,
			0,
			0,
			0
		]],
		["VolumeFlowRate", [
			3,
			0,
			-1,
			0,
			0,
			0,
			0,
			0
		]],
		["VolumetricThermalExpansionCoefficient", [
			0,
			0,
			0,
			0,
			-1,
			0,
			0,
			0
		]],
		["Work", [
			2,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["YieldStrength", [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]],
		["YoungsModulus", [
			-1,
			1,
			-2,
			0,
			0,
			0,
			0,
			0
		]]
	];
	//#endregion
	//#region src/quantity.ts
	/** The unit systems as UnitsApi::getDescriptions lists them: by number, the number UserSchema holds. */
	var SCHEMAS = [...[
		{
			"num": 0,
			"name": "Internal",
			"basic": "mm",
			"multLen": false,
			"multAngle": false,
			"description": "Standard (mm, kg, s, °)",
			"isDefault": true,
			"specs": {
				"Length": [
					[
						1e-6,
						"mm",
						1
					],
					[
						.001,
						"nm",
						1e-6
					],
					[
						.1,
						"µm",
						.001
					],
					[
						1e4,
						"mm",
						1
					],
					[
						1e7,
						"m",
						1e3
					],
					[
						1e10,
						"km",
						1e6
					],
					[
						0,
						"m",
						1e3
					]
				],
				"Area": [
					[
						100,
						"mm^2",
						1
					],
					[
						1e6,
						"cm^2",
						100
					],
					[
						0xe8d4a51000,
						"m^2",
						1e6
					],
					[
						0,
						"km^2",
						0xe8d4a51000
					]
				],
				"Volume": [
					[
						1e3,
						"mm^3",
						1
					],
					[
						1e6,
						"ml",
						1e3
					],
					[
						1e9,
						"l",
						1e6
					],
					[
						0,
						"m^3",
						1e9
					]
				],
				"Angle": [[
					0,
					"°",
					1
				]],
				"ElectricCurrent": [
					[
						1e-6,
						"nA",
						1e-9
					],
					[
						.001,
						"µA",
						1e-6
					],
					[
						1,
						"mA",
						.001
					],
					[
						0,
						"A",
						1
					]
				],
				"Mass": [
					[
						1e-6,
						"µg",
						1e-9
					],
					[
						.001,
						"mg",
						1e-6
					],
					[
						1,
						"g",
						.001
					],
					[
						1e3,
						"kg",
						1
					],
					[
						0,
						"t",
						1e3
					]
				],
				"MassMomentOfInertia": [[
					0,
					"kg*mm^2",
					1
				]],
				"AreaMomentOfInertia": [[
					0,
					"mm^4",
					1
				]],
				"Density": [
					[
						1e-4,
						"kg/m^3",
						1e-9
					],
					[
						1,
						"kg/cm^3",
						.001
					],
					[
						0,
						"kg/mm^3",
						1
					]
				],
				"Concentration": [
					[
						1e-9,
						"µmol/l",
						1e-12
					],
					[
						1e-6,
						"mmol/l",
						1e-9
					],
					[
						0,
						"mol/l",
						1e-6
					]
				],
				"AmountOfSubstance": [
					[
						1e-6,
						"nmol",
						1e-9
					],
					[
						.001,
						"µmol",
						1e-6
					],
					[
						1,
						"mmol",
						.001
					],
					[
						0,
						"mol",
						1
					]
				],
				"ThermalConductivity": [[
					1e6,
					"W/m/K",
					1e3
				], [
					0,
					"W/mm/K",
					1e6
				]],
				"ThermalExpansionCoefficient": [[
					.001,
					"µm/m/K",
					1e-6
				], [
					0,
					"mm/mm/K",
					1
				]],
				"VolumetricThermalExpansionCoefficient": [[
					.001,
					"mm^3/m^3/K",
					1e-9
				], [
					0,
					"m^3/m^3/K",
					1
				]],
				"SpecificHeat": [[
					0,
					"J/kg/K",
					1e6
				]],
				"ThermalTransferCoefficient": [[
					0,
					"W/m^2/K",
					1
				]],
				"Pressure": [
					[
						10,
						"Pa",
						.001
					],
					[
						1e4,
						"kPa",
						1
					],
					[
						1e7,
						"MPa",
						1e3
					],
					[
						1e10,
						"GPa",
						1e6
					],
					[
						0,
						"Pa",
						.001
					]
				],
				"Stress": [
					[
						10,
						"Pa",
						.001
					],
					[
						1e4,
						"kPa",
						1
					],
					[
						1e7,
						"MPa",
						1e3
					],
					[
						1e10,
						"GPa",
						1e6
					],
					[
						0,
						"Pa",
						.001
					]
				],
				"Stiffness": [
					[
						1,
						"mN/m",
						.001
					],
					[
						1e3,
						"N/m",
						1
					],
					[
						1e6,
						"kN/m",
						1e3
					],
					[
						0,
						"MN/m",
						1e6
					]
				],
				"StiffnessDensity": [
					[
						.001,
						"Pa/m",
						1e-6
					],
					[
						1,
						"kPa/m",
						.001
					],
					[
						1e3,
						"MPa/m",
						1
					],
					[
						0,
						"GPa/m",
						1e3
					]
				],
				"Force": [
					[
						1e3,
						"mN",
						1
					],
					[
						1e6,
						"N",
						1e3
					],
					[
						1e9,
						"kN",
						1e6
					],
					[
						0,
						"MN",
						1e9
					]
				],
				"Power": [
					[
						1,
						"nW",
						.001
					],
					[
						1e3,
						"µW",
						1
					],
					[
						1e6,
						"mW",
						1e3
					],
					[
						1e9,
						"W",
						1e6
					],
					[
						0,
						"kW",
						1e9
					]
				],
				"ElectricPotential": [
					[
						1e6,
						"mV",
						1e3
					],
					[
						1e9,
						"V",
						1e6
					],
					[
						0xe8d4a51000,
						"kV",
						1e9
					],
					[
						0,
						"V",
						1e6
					]
				],
				"Work": [
					[
						1602176634e-19,
						"eV",
						1602176634e-22
					],
					[
						1.602176634e-7,
						"keV",
						1602176634e-19
					],
					[
						.0001602176634,
						"MeV",
						1.602176634e-7
					],
					[
						1e6,
						"mJ",
						1e3
					],
					[
						1e9,
						"J",
						1e6
					],
					[
						0xe8d4a51000,
						"kJ",
						1e9
					],
					[
						0xcca2e51310000,
						"kWh",
						36e11
					],
					[
						0,
						"J",
						1e6
					]
				],
				"Moment": [[
					0,
					"Nm",
					1e6
				]],
				"SpecificEnergy": [[
					0,
					"m^2/s^2",
					1e6
				]],
				"HeatFlux": [[
					0,
					"W/m^2",
					1
				]],
				"ElectricCharge": [[
					0,
					"C",
					1
				]],
				"SurfaceChargeDensity": [
					[
						.01,
						"C/m^2",
						1e-6
					],
					[
						1,
						"C/cm^2",
						.01
					],
					[
						0,
						"C/mm^2",
						1
					]
				],
				"VolumeChargeDensity": [
					[
						.001,
						"C/m^3",
						1e-9
					],
					[
						1,
						"C/cm^3",
						.001
					],
					[
						0,
						"C/mm^3",
						1
					]
				],
				"CurrentDensity": [
					[
						.01,
						"A/m^2",
						1e-6
					],
					[
						1,
						"A/cm^2",
						.01
					],
					[
						0,
						"A/mm^2",
						1
					]
				],
				"MagneticFluxDensity": [[
					1,
					"mT",
					.001
				], [
					0,
					"T",
					1
				]],
				"MagneticFieldStrength": [[
					0,
					"A/m",
					.001
				]],
				"MagneticFlux": [[
					0,
					"Wb",
					1e6
				]],
				"Magnetization": [[
					0,
					"A/m",
					.001
				]],
				"ElectromagneticPotential": [[
					0,
					"Wb/m",
					1e3
				]],
				"ElectricalConductance": [
					[
						1e-9,
						"µS",
						1e-12
					],
					[
						1e-6,
						"mS",
						1e-9
					],
					[
						0,
						"S",
						1e-6
					]
				],
				"ElectricalResistance": [
					[
						1e9,
						"Ohm",
						1e6
					],
					[
						0xe8d4a51000,
						"kOhm",
						1e9
					],
					[
						0,
						"MOhm",
						0xe8d4a51000
					]
				],
				"ElectricalConductivity": [
					[
						1e-9,
						"mS/m",
						1e-12
					],
					[
						1e-6,
						"S/m",
						1e-9
					],
					[
						.001,
						"kS/m",
						1e-6
					],
					[
						0,
						"MS/m",
						.001
					]
				],
				"ElectricalCapacitance": [
					[
						1e-15,
						"pF",
						1e-18
					],
					[
						1e-12,
						"nF",
						1e-15
					],
					[
						1e-9,
						"µF",
						1e-12
					],
					[
						1e-6,
						"mF",
						1e-9
					],
					[
						0,
						"F",
						1e-6
					]
				],
				"ElectricalInductance": [
					[
						1,
						"nH",
						.001
					],
					[
						1e3,
						"µH",
						1
					],
					[
						1e6,
						"mH",
						1e3
					],
					[
						0,
						"H",
						1e6
					]
				],
				"VacuumPermittivity": [[
					0,
					"F/m",
					1e-9
				]],
				"Frequency": [
					[
						1e3,
						"Hz",
						1
					],
					[
						1e6,
						"kHz",
						1e3
					],
					[
						1e9,
						"MHz",
						1e6
					],
					[
						0xe8d4a51000,
						"GHz",
						1e9
					],
					[
						0,
						"THz",
						0xe8d4a51000
					]
				],
				"Velocity": [[
					0,
					"mm/s",
					1
				]],
				"DynamicViscosity": [[
					0,
					"Pa*s",
					.001
				]],
				"KinematicViscosity": [[
					1e3,
					"mm^2/s",
					1
				], [
					0,
					"m^2/s",
					1e6
				]],
				"VolumeFlowRate": [
					[
						1e3,
						"mm^3/s",
						1
					],
					[
						1e6,
						"ml/s",
						1e3
					],
					[
						1e9,
						"l/s",
						1e6
					],
					[
						0,
						"m^3/s",
						1e9
					]
				],
				"DissipationRate": [[
					0,
					"W/kg",
					1e6
				]],
				"InverseLength": [
					[
						1e-6,
						"1/m",
						.001
					],
					[
						.001,
						"1/km",
						1e-6
					],
					[
						1,
						"1/m",
						.001
					],
					[
						1e3,
						"1/mm",
						1
					],
					[
						1e6,
						"1/µm",
						1e3
					],
					[
						1e9,
						"1/nm",
						1e6
					],
					[
						0,
						"1/m",
						.001
					]
				],
				"InverseArea": [
					[
						1e-12,
						"1/m^2",
						1e-6
					],
					[
						1e-6,
						"1/km^2",
						1e-12
					],
					[
						1,
						"1/m^2",
						1e-6
					],
					[
						100,
						"1/cm^2",
						.01
					],
					[
						0,
						"1/mm^2",
						1
					]
				],
				"InverseVolume": [
					[
						1e-6,
						"1/m^3",
						1e-9
					],
					[
						.001,
						"1/l",
						1e-6
					],
					[
						1,
						"1/ml",
						.001
					],
					[
						0,
						"1/mm^3",
						1
					]
				]
			}
		},
		{
			"num": 1,
			"name": "MKS",
			"basic": "m",
			"multLen": false,
			"multAngle": false,
			"description": "MKS (m, kg, s, °)",
			"isDefault": false,
			"specs": {
				"Length": [
					[
						1e-6,
						"mm",
						1
					],
					[
						.001,
						"nm",
						1e-6
					],
					[
						.1,
						"µm",
						.001
					],
					[
						1e4,
						"mm",
						1
					],
					[
						1e7,
						"m",
						1e3
					],
					[
						1e10,
						"km",
						1e6
					],
					[
						0,
						"m",
						1e3
					]
				],
				"Area": [
					[
						100,
						"mm^2",
						1
					],
					[
						1e6,
						"cm^2",
						100
					],
					[
						0xe8d4a51000,
						"m^2",
						1e6
					],
					[
						0,
						"km^2",
						0xe8d4a51000
					]
				],
				"Volume": [
					[
						1e3,
						"mm^3",
						1
					],
					[
						1e6,
						"ml",
						1e3
					],
					[
						1e9,
						"l",
						1e6
					],
					[
						0,
						"m^3",
						1e9
					]
				],
				"Mass": [
					[
						1e-6,
						"µg",
						1e-9
					],
					[
						.001,
						"mg",
						1e-6
					],
					[
						1,
						"g",
						.001
					],
					[
						1e3,
						"kg",
						1
					],
					[
						0,
						"t",
						1e3
					]
				],
				"MassMomentOfInertia": [[
					0,
					"kg*m^2",
					1e6
				]],
				"AreaMomentOfInertia": [
					[
						1e4,
						"mm^4",
						1
					],
					[
						1e10,
						"cm^4",
						1e4
					],
					[
						0,
						"m^4",
						0xe8d4a51000
					]
				],
				"Density": [
					[
						1e-4,
						"kg/m^3",
						1e-9
					],
					[
						1,
						"kg/cm^3",
						.001
					],
					[
						0,
						"kg/mm^3",
						1
					]
				],
				"Acceleration": [[
					0,
					"m/s^2",
					1e3
				]],
				"Pressure": [
					[
						10,
						"Pa",
						.001
					],
					[
						1e4,
						"kPa",
						1
					],
					[
						1e7,
						"MPa",
						1e3
					],
					[
						1e10,
						"GPa",
						1e6
					],
					[
						0,
						"Pa",
						.001
					]
				],
				"Stress": [
					[
						10,
						"Pa",
						.001
					],
					[
						1e4,
						"kPa",
						1
					],
					[
						1e7,
						"MPa",
						1e3
					],
					[
						1e10,
						"GPa",
						1e6
					],
					[
						0,
						"Pa",
						.001
					]
				],
				"Stiffness": [
					[
						1,
						"mN/m",
						.001
					],
					[
						1e3,
						"N/m",
						1
					],
					[
						1e6,
						"kN/m",
						1e3
					],
					[
						0,
						"MN/m",
						1e6
					]
				],
				"StiffnessDensity": [
					[
						.001,
						"Pa/m",
						1e-6
					],
					[
						1,
						"kPa/m",
						.001
					],
					[
						1e3,
						"MPa/m",
						1
					],
					[
						0,
						"GPa/m",
						1e3
					]
				],
				"ThermalConductivity": [[
					1e6,
					"W/m/K",
					1e3
				], [
					0,
					"W/mm/K",
					1e6
				]],
				"ThermalExpansionCoefficient": [[
					.001,
					"µm/m/K",
					1e-6
				], [
					0,
					"m/m/K",
					1
				]],
				"VolumetricThermalExpansionCoefficient": [[
					.001,
					"mm^3/m^3/K",
					1e-9
				], [
					0,
					"m^3/m^3/K",
					1
				]],
				"SpecificHeat": [[
					0,
					"J/kg/K",
					1e6
				]],
				"ThermalTransferCoefficient": [[
					0,
					"W/m^2/K",
					1
				]],
				"Force": [
					[
						1e3,
						"mN",
						1
					],
					[
						1e6,
						"N",
						1e3
					],
					[
						1e9,
						"kN",
						1e6
					],
					[
						0,
						"MN",
						1e9
					]
				],
				"Power": [
					[
						1e6,
						"mW",
						1e3
					],
					[
						1e9,
						"W",
						1e6
					],
					[
						0,
						"kW",
						1e9
					]
				],
				"ElectricPotential": [
					[
						1e6,
						"mV",
						1e3
					],
					[
						1e9,
						"V",
						1e6
					],
					[
						0xe8d4a51000,
						"kV",
						1e9
					],
					[
						0,
						"V",
						1e6
					]
				],
				"ElectricCharge": [[
					0,
					"C",
					1
				]],
				"SurfaceChargeDensity": [[
					0,
					"C/m^2",
					1e-6
				]],
				"VolumeChargeDensity": [[
					0,
					"C/m^3",
					1e-9
				]],
				"CurrentDensity": [[
					1,
					"A/m^2",
					1e-6
				], [
					0,
					"A/mm^2",
					1
				]],
				"MagneticFluxDensity": [[
					1,
					"mT",
					.001
				], [
					0,
					"T",
					1
				]],
				"MagneticFieldStrength": [[
					0,
					"A/m",
					.001
				]],
				"MagneticFlux": [[
					0,
					"Wb",
					1e6
				]],
				"Magnetization": [[
					0,
					"A/m",
					.001
				]],
				"ElectromagneticPotential": [[
					0,
					"Wb/m",
					1e3
				]],
				"ElectricalConductance": [
					[
						1e-9,
						"µS",
						1e-12
					],
					[
						1e-6,
						"mS",
						1e-9
					],
					[
						0,
						"S",
						1e-6
					]
				],
				"ElectricalResistance": [
					[
						1e9,
						"Ohm",
						1e6
					],
					[
						0xe8d4a51000,
						"kOhm",
						1e9
					],
					[
						0,
						"MOhm",
						0xe8d4a51000
					]
				],
				"ElectricalConductivity": [
					[
						1e-9,
						"mS/m",
						1e-12
					],
					[
						1e-6,
						"S/m",
						1e-9
					],
					[
						.001,
						"kS/m",
						1e-6
					],
					[
						0,
						"MS/m",
						.001
					]
				],
				"ElectricalCapacitance": [
					[
						1e-15,
						"pF",
						1e-18
					],
					[
						1e-12,
						"nF",
						1e-15
					],
					[
						1e-9,
						"µF",
						1e-12
					],
					[
						1e-6,
						"mF",
						1e-9
					],
					[
						0,
						"F",
						1e-6
					]
				],
				"ElectricalInductance": [
					[
						1,
						"nH",
						.001
					],
					[
						1e3,
						"µH",
						1
					],
					[
						1e6,
						"mH",
						1e3
					],
					[
						0,
						"H",
						1e6
					]
				],
				"VacuumPermittivity": [[
					0,
					"F/m",
					1e-9
				]],
				"Work": [
					[
						1602176634e-19,
						"eV",
						1602176634e-22
					],
					[
						1.602176634e-7,
						"keV",
						1602176634e-19
					],
					[
						.0001602176634,
						"MeV",
						1.602176634e-7
					],
					[
						1e6,
						"mJ",
						1e3
					],
					[
						1e9,
						"J",
						1e6
					],
					[
						0xe8d4a51000,
						"kJ",
						1e9
					],
					[
						0xcca2e51310000,
						"kWh",
						36e11
					],
					[
						0,
						"J",
						1e6
					]
				],
				"SpecificEnergy": [[
					0,
					"m^2/s^2",
					1e6
				]],
				"HeatFlux": [[
					0,
					"W/m^2",
					1
				]],
				"Frequency": [
					[
						1e3,
						"Hz",
						1
					],
					[
						1e6,
						"kHz",
						1e3
					],
					[
						1e9,
						"MHz",
						1e6
					],
					[
						0xe8d4a51000,
						"GHz",
						1e9
					],
					[
						0,
						"THz",
						0xe8d4a51000
					]
				],
				"Velocity": [[
					0,
					"m/s",
					1e3
				]],
				"DynamicViscosity": [[
					0,
					"Pa*s",
					.001
				]],
				"KinematicViscosity": [[
					0,
					"m^2/s",
					1e6
				]],
				"VolumeFlowRate": [
					[
						.001,
						"m^3/s",
						1e9
					],
					[
						1e3,
						"mm^3/s",
						1
					],
					[
						1e6,
						"ml/s",
						1e3
					],
					[
						1e9,
						"l/s",
						1e6
					],
					[
						0,
						"m^3/s",
						1e9
					]
				],
				"DissipationRate": [[
					0,
					"W/kg",
					1e6
				]],
				"InverseLength": [
					[
						1e-6,
						"1/m",
						.001
					],
					[
						.001,
						"1/km",
						1e-6
					],
					[
						1,
						"1/m",
						.001
					],
					[
						1e3,
						"1/mm",
						1
					],
					[
						1e6,
						"1/µm",
						1e3
					],
					[
						1e9,
						"1/nm",
						1e6
					],
					[
						0,
						"1/m",
						.001
					]
				],
				"InverseArea": [
					[
						1e-12,
						"1/m^2",
						1e-6
					],
					[
						1e-6,
						"1/km^2",
						1e-12
					],
					[
						1,
						"1/m^2",
						1e-6
					],
					[
						100,
						"1/cm^2",
						.01
					],
					[
						0,
						"1/mm^2",
						1
					]
				],
				"InverseVolume": [
					[
						1e-6,
						"1/m^3",
						1e-9
					],
					[
						.001,
						"1/l",
						1e-6
					],
					[
						1,
						"1/ml",
						.001
					],
					[
						0,
						"1/mm^3",
						1
					]
				]
			}
		},
		{
			"num": 4,
			"name": "Centimeter",
			"basic": "cm",
			"multLen": false,
			"multAngle": false,
			"description": "Building Euro (cm, m², m³)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"cm",
					10
				]],
				"Area": [[
					0,
					"m^2",
					1e6
				]],
				"Volume": [[
					0,
					"m^3",
					1e9
				]],
				"MassMomentOfInertia": [[
					0,
					"kg*cm^2",
					100
				]],
				"AreaMomentOfInertia": [[
					0,
					"cm^4",
					1e4
				]],
				"Power": [[
					0,
					"W",
					1e6
				]],
				"ElectricPotential": [[
					0,
					"V",
					1e6
				]],
				"HeatFlux": [[
					0,
					"W/m^2",
					1
				]],
				"Velocity": [[
					0,
					"mm/min",
					.016666666666666666
				]]
			}
		},
		{
			"num": 8,
			"name": "FEM",
			"basic": "mm",
			"multLen": false,
			"multAngle": false,
			"description": "FEM (mm, N, s)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"mm",
					1
				]],
				"Area": [[
					0,
					"mm^2",
					1
				]],
				"Volume": [[
					0,
					"mm^3",
					1
				]],
				"Mass": [[
					0,
					"t",
					1e3
				]],
				"Inertia": [[
					0,
					"t*mm^2",
					1e3
				]],
				"Density": [[
					0,
					"kg/m^3",
					1e-9
				]],
				"Acceleration": [[
					0,
					"mm/s^2",
					1
				]],
				"Pressure": [[
					10,
					"kPa",
					1
				], [
					0,
					"MPa",
					1e3
				]],
				"Stress": [[
					10,
					"kPa",
					1
				], [
					0,
					"MPa",
					1e3
				]],
				"Stiffness": [[
					0,
					"N/mm",
					1e3
				]],
				"StiffnessDensity": [[
					0,
					"MPa/mm",
					1e3
				]],
				"ThermalConductivity": [[
					0,
					"mW/mm/K",
					1e3
				]],
				"ThermalExpansionCoefficient": [[
					0,
					"µm/m/K",
					1e-6
				]],
				"VolumetricThermalExpansionCoefficient": [[
					0,
					"mm^3/m^3/K",
					1e-9
				]],
				"SpecificHeat": [[
					0,
					"mJ/t/K",
					1
				]],
				"ThermalTransferCoefficient": [[
					0,
					"mW/mm^2/K",
					1e3
				]],
				"Force": [[
					0,
					"N",
					1e3
				]],
				"Power": [[
					0,
					"mW",
					1e3
				]],
				"ElectricPotential": [[
					0,
					"mV",
					1e3
				]],
				"ElectricCharge": [[
					0,
					"C",
					1
				]],
				"SurfaceChargeDensity": [[
					0,
					"C/mm^2",
					1
				]],
				"VolumeChargeDensity": [[
					0,
					"C/mm^3",
					1
				]],
				"CurrentDensity": [[
					0,
					"A/mm^2",
					1
				]],
				"MagneticFluxDensity": [[
					0,
					"mT",
					.001
				]],
				"MagneticFieldStrength": [[
					0,
					"A/mm",
					1
				]],
				"MagneticFlux": [[
					0,
					"mJ/A",
					1e3
				]],
				"Magnetization": [[
					0,
					"A/mm",
					1
				]],
				"ElectromagneticPotential": [[
					0,
					"mJ/A/mm",
					1e3
				]],
				"ElectricalConductance": [[
					0,
					"kS",
					.001
				]],
				"ElectricalResistance": [[
					0,
					"Ohm",
					1e6
				]],
				"ElectricalConductivity": [[
					0,
					"kS/mm",
					.001
				]],
				"ElectricalCapacitance": [[
					0,
					"C/mV",
					.001
				]],
				"ElectricalInductance": [[
					0,
					"mH",
					1e3
				]],
				"VacuumPermittivity": [[
					0,
					"C/mV/mm",
					.001
				]],
				"Work": [[
					0,
					"mJ",
					1e3
				]],
				"Moment": [[
					0,
					"Nmm",
					1e3
				]],
				"SpecificEnergy": [[
					0,
					"mJ/t",
					1
				]],
				"HeatFlux": [[
					0,
					"mW/mm^2",
					1e3
				]],
				"Frequency": [[
					0,
					"Hz",
					1
				]],
				"Velocity": [[
					0,
					"mm/s",
					1
				]],
				"DynamicViscosity": [[
					0,
					"MPa*s",
					1e3
				]],
				"KinematicViscosity": [[
					0,
					"mm^2/s",
					1
				]],
				"VolumeFlowRate": [[
					0,
					"mm^3/s",
					1
				]],
				"DissipationRate": [[
					0,
					"mW/t",
					1
				]],
				"InverseLength": [[
					0,
					"1/mm",
					1
				]],
				"InverseArea": [[
					0,
					"1/mm^2",
					1
				]],
				"InverseVolume": [[
					0,
					"1/mm^3",
					1
				]],
				"Angle": [[
					0,
					"°",
					1
				]]
			}
		},
		{
			"num": 2,
			"name": "Imperial",
			"basic": "in",
			"multLen": false,
			"multAngle": false,
			"description": "US customary (in, lb)",
			"isDefault": false,
			"specs": {
				"Length": [
					[
						254e-8,
						"in",
						25.4
					],
					[
						2.54,
						"thou",
						.0254
					],
					[
						304.8,
						"\"",
						25.4
					],
					[
						914.4,
						"'",
						304.79999999999995
					],
					[
						1609344,
						"yd",
						914.3999999999999
					],
					[
						1609344e3,
						"mi",
						1609343.9999999998
					],
					[
						0,
						"in",
						25.4
					]
				],
				"Angle": [[
					0,
					"°",
					1
				]],
				"Area": [[
					0,
					"in^2",
					645.16
				]],
				"Density": [[
					0,
					"lb/in^3",
					27679904710203126e-21
				]],
				"Volume": [[
					0,
					"in^3",
					16387.064
				]],
				"Mass": [[
					0,
					"lb",
					.45359237
				]],
				"MassMomentOfInertia": [[
					0,
					"lb*in^2",
					292.6396534292
				]],
				"AreaMomentOfInertia": [[
					0,
					"in^4",
					416231.42559999996
				]],
				"Pressure": [
					[
						6894.757293168361,
						"psi",
						6.894757293168361
					],
					[
						6894757.293168361,
						"ksi",
						6894.757293168361
					],
					[
						0,
						"psi",
						6.894757293168361
					]
				],
				"Stiffness": [[
					0,
					"lbf/in",
					175.1268352464764
				]],
				"Velocity": [[
					0,
					"in/min",
					.4233333333333333
				]]
			}
		},
		{
			"num": 5,
			"name": "ImperialBuilding",
			"basic": "ft",
			"multLen": true,
			"multAngle": false,
			"description": "Building US (ft-in, sqft, cft)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"toFractional",
					0
				]],
				"Angle": [[
					0,
					"°",
					1
				]],
				"Area": [[
					0,
					"sqft",
					92903.03999999998
				]],
				"Volume": [[
					0,
					"cft",
					28316846.59199999
				]],
				"Density": [[
					0,
					"lb/ft^3",
					1.6018463373960146e-8
				]],
				"Pressure": [[
					0,
					"psi",
					6.894757293168361
				]],
				"Velocity": [[
					0,
					"in/min",
					.4233333333333333
				]]
			}
		},
		{
			"num": 7,
			"name": "ImperialCivil",
			"basic": "ft",
			"multLen": false,
			"multAngle": true,
			"description": "Imperial for Civil Eng (ft, lb, mph)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"ft",
					304.79999999999995
				]],
				"Area": [[
					0,
					"ft^2",
					92903.03999999998
				]],
				"Volume": [[
					0,
					"ft^3",
					28316846.59199999
				]],
				"Mass": [[
					0,
					"lb",
					.45359237
				]],
				"MassMomentOfInertia": [[
					0,
					"lb*ft^2",
					42140.11009380478
				]],
				"AreaMomentOfInertia": [[
					0,
					"ft^4",
					8630974841.241596
				]],
				"Density": [[
					0,
					"lb/ft^3",
					1.6018463373960146e-8
				]],
				"Pressure": [[
					0,
					"psi",
					6.894757293168361
				]],
				"Stiffness": [[
					0,
					"lbf/in",
					175.1268352464764
				]],
				"Velocity": [[
					0,
					"mph",
					447.03999999999996
				]],
				"Angle": [[
					0,
					"toDMS",
					0
				]]
			}
		},
		{
			"num": 6,
			"name": "MmMin",
			"basic": "mm",
			"multLen": false,
			"multAngle": false,
			"description": "Metric small parts & CNC (mm, mm/min)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"mm",
					1
				]],
				"Angle": [[
					0,
					"°",
					1
				]],
				"Velocity": [[
					0,
					"mm/min",
					.016666666666666666
				]]
			}
		},
		{
			"num": 9,
			"name": "MeterDecimal",
			"basic": "m",
			"multLen": false,
			"multAngle": false,
			"description": "Meter decimal (m, m², m³)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"m",
					1e3
				]],
				"Area": [[
					0,
					"m^2",
					1e6
				]],
				"Volume": [[
					0,
					"m^3",
					1e9
				]],
				"MassMomentOfInertia": [[
					0,
					"kg*m^2",
					1e6
				]],
				"AreaMomentOfInertia": [[
					0,
					"m^4",
					0xe8d4a51000
				]],
				"Power": [[
					0,
					"W",
					1e6
				]],
				"ElectricPotential": [[
					0,
					"V",
					1e6
				]],
				"HeatFlux": [[
					0,
					"W/m^2",
					1
				]],
				"Velocity": [[
					0,
					"m/s",
					1e3
				]]
			}
		},
		{
			"num": 3,
			"name": "ImperialDecimal",
			"basic": "in",
			"multLen": false,
			"multAngle": false,
			"description": "Imperial decimal (in, lb)",
			"isDefault": false,
			"specs": {
				"Length": [[
					0,
					"in",
					25.4
				]],
				"Angle": [[
					0,
					"°",
					1
				]],
				"Area": [[
					0,
					"in^2",
					645.16
				]],
				"Volume": [[
					0,
					"in^3",
					16387.064
				]],
				"Mass": [[
					0,
					"lb",
					.45359237
				]],
				"MassMomentOfInertia": [[
					0,
					"lb*in^2",
					292.6396534292
				]],
				"AreaMomentOfInertia": [[
					0,
					"in^4",
					416231.42559999996
				]],
				"Pressure": [[
					0,
					"psi",
					6.894757293168361
				]],
				"Stiffness": [[
					0,
					"lbf/in",
					175.1268352464764
				]],
				"Velocity": [[
					0,
					"in/min",
					.4233333333333333
				]],
				"Acceleration": [[
					0,
					"in/min^2",
					.007055555555555555
				]]
			}
		}
	]].sort((a, b) => a.num - b.num);
	var ZERO$2 = [
		0,
		0,
		0,
		0,
		0,
		0,
		0,
		0
	];
	var SYMBOLS = [
		"mm",
		"kg",
		"s",
		"A",
		"K",
		"mol",
		"cd",
		"deg"
	];
	var FUNCS = {
		acos: Math.acos,
		asin: Math.asin,
		atan: Math.atan,
		abs: Math.abs,
		exp: Math.exp,
		log: Math.log,
		log10: Math.log10,
		sin: Math.sin,
		sinh: Math.sinh,
		tan: Math.tan,
		tanh: Math.tanh,
		sqrt: Math.sqrt,
		cos: Math.cos
	};
	var DEAD = [
		"atan2",
		"mod",
		"pow"
	];
	var WORDS = [
		...Object.keys(UNITS),
		...Object.keys(FUNCS),
		...DEAD,
		"pi",
		"e"
	];
	var NUMBER = [
		/^\d+\.?\d*(?:[eE][-+]?\d+)?/,
		/^\.?\d+(?:[eE][-+]?\d+)?/,
		/^\d+,?\d*(?:[eE][-+]?\d+)?/,
		/^,?\d+(?:[eE][-+]?\d+)?/
	];
	/** std::numeric_limits<double>::min(), what Quantity::parse returns for empty input. */
	var DBL_MIN = 22250738585072014e-324;
	/** A parse failure ('syntax'), Base::UnitsMismatchError ('mismatch') or another evaluation error. */
	var QuantityError = class extends Error {
		kind;
		constructor(message, kind = "syntax") {
			super(message);
			this.kind = kind;
		}
	};
	/** Quantity.l: flex takes the longest match; on a tie the earlier rule (units first). */
	function lex(text) {
		const out = [];
		let i = 0;
		while (i < text.length) {
			const rest = text.slice(i), c = rest[0];
			if (c === "[") {
				const j = text.indexOf("]", i);
				if (j < 0) throw new QuantityError("Unterminated quantity comment");
				i = j + 1;
				continue;
			}
			if (/\s/.test(c)) {
				i++;
				continue;
			}
			let best = "", tok = null;
			for (const w of WORDS) if (w.length > best.length && rest.startsWith(w)) {
				best = w;
				tok = w in UNITS ? {
					t: "UNIT",
					q: {
						value: UNITS[w][0],
						dims: UNITS[w][1]
					}
				} : w === "pi" ? {
					t: "NUM",
					v: Math.PI
				} : w === "e" ? {
					t: "NUM",
					v: Math.E
				} : {
					t: "FN",
					v: WORDS.indexOf(w)
				};
				if (tok.t === "FN") tok.name = w;
			}
			for (const re of NUMBER) {
				const m = re.exec(rest);
				if (m && m[0].length > best.length) {
					best = m[0];
					tok = {
						t: "NUM",
						v: Number(m[0].replace(",", "."))
					};
				}
			}
			if (best === "1") tok = {
				t: "ONE",
				v: 1
			};
			if (!tok) {
				if ("+()=/*^".includes(c)) {
					best = c;
					tok = { t: c };
				} else if (c === "-" || c === "−") {
					best = c;
					tok = { t: "-" };
				} else if (c.charCodeAt(0) >= 128) break;
				else throw new QuantityError("syntax error");
			}
			out.push(tok);
			i += best.length;
		}
		return out;
	}
	var num = (v, one = false) => ({
		kind: "num",
		q: {
			value: v,
			dims: ZERO$2
		},
		one
	});
	/** Unit.h's checkRange(): each dimension's exponent must stay within ±unitExponentLimit (8). */
	function checkRange$1(dims) {
		for (const d of dims) {
			if (d >= 8) throw new QuantityError("Unit exponent overflow", "eval");
			if (d < -8) throw new QuantityError("Unit exponent underflow", "eval");
		}
		return dims;
	}
	var mul = (a, b) => ({
		value: a.value * b.value,
		dims: checkRange$1(a.dims.map((d, i) => d + b.dims[i]))
	});
	var div = (a, b) => ({
		value: a.value / b.value,
		dims: checkRange$1(a.dims.map((d, i) => d - b.dims[i]))
	});
	/** Quantity::pow(const Quantity&), for `unit '^' num`: the value is raised to the exponent, the
	*  unit to static_cast<signed char>(exponent) — truncated, so "m^0.5" is a plain number. */
	function pow(a, e) {
		const n = Math.trunc(e) << 24 >> 24;
		return {
			value: Math.pow(a.value, e),
			dims: checkRange$1(a.dims.map((d) => d * n))
		};
	}
	var sameDims$1 = (a, b) => a.every((d, i) => d === b[i]);
	/** Quantity.y: input is a number, a unit, or up to three quantities added (num unit, num / unit). */
	function parseQuantity(text) {
		const toks = lex(text);
		if (!toks.length) return {
			value: DBL_MIN,
			dims: ZERO$2
		};
		let p = 0;
		const peek = () => toks[p];
		const eat = (t) => {
			if (toks[p]?.t !== t) throw new QuantityError("syntax error");
			return toks[p++];
		};
		const startsUnit = (k = p) => toks[k]?.t === "UNIT" || toks[k]?.t === "(" && startsUnit(k + 1) || toks[k]?.t === "ONE" && toks[k + 1]?.t === "/" && startsUnit(k + 2);
		const PREC = {
			"+": 1,
			"-": 1,
			"*": 2,
			"/": 2,
			"^": 4
		};
		function numPrimary() {
			const t = peek();
			if (!t) throw new QuantityError("syntax error");
			if (t.t === "NUM") {
				p++;
				return num(t.v);
			}
			if (t.t === "ONE") {
				p++;
				return num(1, true);
			}
			if (t.t === "+" || t.t === "-") {
				p++;
				const v = numExpr(3);
				return num(t.t === "-" ? -v.q.value : v.q.value);
			}
			if (t.t === "(") {
				p++;
				const v = numExpr(0);
				eat(")");
				return v;
			}
			if (t.t === "FN") {
				const name = t.name;
				if (!(name in FUNCS)) throw new QuantityError("syntax error");
				p++;
				eat("(");
				const v = numExpr(0);
				eat(")");
				return num(FUNCS[name](v.q.value));
			}
			throw new QuantityError("syntax error");
		}
		function numExpr(min) {
			let left = numPrimary();
			for (;;) {
				const t = peek();
				if (!t || !(t.t in PREC) || PREC[t.t] < min) return left;
				if (t.t === "/" && startsUnit(p + 1)) return left;
				p++;
				const right = numExpr(t.t === "^" ? PREC[t.t] : PREC[t.t] + 1);
				const a = left.q.value, b = right.q.value;
				left = num(t.t === "+" ? a + b : t.t === "-" ? a - b : t.t === "*" ? a * b : t.t === "/" ? a / b : Math.pow(a, b));
			}
		}
		function unitPrimary() {
			const t = peek();
			if (t?.t === "UNIT") {
				p++;
				return t.q;
			}
			if (t?.t === "ONE" && toks[p + 1]?.t === "/") {
				p += 2;
				return div({
					value: 1,
					dims: ZERO$2
				}, unitExpr(3));
			}
			if (t?.t === "(") {
				p++;
				const u = unitExpr(0);
				eat(")");
				return u;
			}
			throw new QuantityError("syntax error");
		}
		function unitExpr(min) {
			let left = unitPrimary();
			for (;;) {
				const t = peek();
				if (!t) return left;
				if (t.t === "^" && 4 >= min) {
					p++;
					left = pow(left, numExpr(4).q.value);
					continue;
				}
				if ((t.t === "*" || t.t === "/") && 2 >= min && startsUnit(p + 1)) {
					p++;
					const r = unitExpr(3);
					left = t.t === "*" ? mul(left, r) : div(left, r);
					continue;
				}
				return left;
			}
		}
		function quantity() {
			if (startsUnit()) return {
				kind: "unit",
				q: unitExpr(0)
			};
			const n = numExpr(0);
			if (!peek()) return n;
			if (peek().t === "/" && startsUnit(p + 1)) {
				p++;
				return {
					kind: "quantity",
					q: div(n.q, unitExpr(0))
				};
			}
			if (startsUnit()) return {
				kind: "quantity",
				q: mul(n.q, unitExpr(0))
			};
			throw new QuantityError("syntax error");
		}
		const first = quantity();
		if (first.kind !== "quantity") {
			if (p < toks.length) throw new QuantityError("syntax error");
			return first.q;
		}
		let sum = first.q;
		for (let k = 1; k < 3 && p < toks.length; k++) {
			const next = quantity();
			if (next.kind !== "quantity") throw new QuantityError("syntax error");
			if (!sameDims$1(sum.dims, next.q.dims)) throw new QuantityError("Quantity::operator +(): Unit mismatch in plus operation", "mismatch");
			sum = {
				value: sum.value + next.q.value,
				dims: sum.dims
			};
		}
		if (p < toks.length) throw new QuantityError("syntax error");
		return sum;
	}
	/** Unit::getTypeString: the name of the quantity type, or ''. */
	var typeString = (dims) => UNIT_TYPES.find(([, d]) => sameDims$1(d, dims))?.[0] ?? "";
	/** Unit::getString: mm^2, kg/(mm*s^2), 1/mm. */
	function unitString(dims) {
		const part = (i) => Math.abs(dims[i]) <= 1 ? SYMBOLS[i] : `${SYMBOLS[i]}^${Math.abs(dims[i])}`;
		const pos = dims.map((d, i) => d > 0 ? i : -1).filter((i) => i >= 0), neg = dims.map((d, i) => d < 0 ? i : -1).filter((i) => i >= 0);
		const numr = pos.map(part).join("*");
		if (!neg.length) return numr;
		const den = neg.map(part).join("*");
		return `${numr || "1"}/${neg.length > 1 ? `(${den})` : den}`;
	}
	/** toFractional: feet, inches and fractions of an inch, for Building US. */
	function toFractional(value, denominator) {
		let n = Math.round(Math.abs(value) / 25.4 * denominator);
		if (n === 0) return "0";
		const feet = Math.floor(n / (12 * denominator));
		n -= 12 * denominator * feet;
		const inches = Math.floor(n / denominator);
		let numerator = n - denominator * inches;
		const gcd = (a, b) => b === 0 ? a : gcd(b, a % b);
		const g = gcd(numerator, denominator);
		numerator /= g;
		const den = denominator / g;
		let out = value < 0 ? "-" : "", space = false;
		if (feet > 0) {
			out += `${feet}'`;
			space = true;
		}
		if (inches > 0) {
			out += `${space ? " " : ""}${inches}"`;
			space = false;
		}
		if (numerator > 0) {
			if (inches > 0) {
				out += ` ${value < 0 ? "-" : "+"} `;
				space = false;
			}
			out += `${space ? " " : ""}${numerator}/${den}"`;
		}
		return out;
	}
	/** toDms: degrees, minutes and seconds. */
	function toDms(value) {
		const split = (t) => {
			const w = Math.floor(t);
			return [w, 60 * (t - w)];
		};
		const [deg, mins] = split(value);
		let out = `${deg}°`;
		if (mins > 0) {
			const [m, secs] = split(mins);
			out += `${m}′`;
			if (secs > 0) out += `${Math.round(secs)}″`;
		}
		return out;
	}
	/** UnitsApi's current schema, decimals and fraction denominator (Preferences > General > Units). */
	var unitPrefs = {
		schema: 0,
		decimals: 2,
		denominator: 8
	};
	/** `digits` (value = d0.d1d2… × 10^exp) rounded half to even at `decimals` fraction digits,
	*  scaled by 10^decimals. */
	function roundHalfEven(digits, exp, decimals) {
		const keep = exp + 1 + decimals;
		if (keep >= digits.length) return BigInt(digits) * 10n ** BigInt(keep - digits.length);
		if (keep < 0) return 0n;
		let n = keep ? BigInt(digits.slice(0, keep)) : 0n;
		const next = digits[keep], rest = digits.slice(keep + 1);
		if (next > "5" || next === "5" && (/[1-9]/.test(rest) || n % 2n === 1n)) n += 1n;
		return n;
	}
	/** n / 10^decimals written out: "1234" with 2 → "12.34". */
	function pointed(n, decimals) {
		const t = n.toString().padStart(decimals + 1, "0");
		return decimals ? `${t.slice(0, -decimals)}.${t.slice(-decimals)}` : t;
	}
	/** The shortest decimal digits that read back as the same double (what ICU formats from). */
	function shortestDigits(v) {
		const [m, e] = Math.abs(v).toExponential().split("e");
		return {
			digits: m.replace(".", ""),
			exp: Number(e)
		};
	}
	/** A double's exact decimal digits (what printf rounds): m × 2^p, written out with BigInt. */
	function exactDigits(v) {
		if (v === 0) return {
			digits: "0",
			exp: 0
		};
		const view = /* @__PURE__ */ new DataView(/* @__PURE__ */ new ArrayBuffer(8));
		view.setFloat64(0, Math.abs(v));
		const hi = view.getUint32(0), lo = view.getUint32(4), e = hi >>> 20 & 2047;
		let m = BigInt(hi & 1048575) << 32n | BigInt(lo), p = -1074;
		if (e) {
			m |= 1n << 52n;
			p = e - 1075;
		}
		const s = p >= 0 ? (m << BigInt(p)).toString() : (m * 5n ** BigInt(-p)).toString();
		return {
			digits: s.replace(/0+$/, "") || "0",
			exp: s.length - 1 - (p >= 0 ? 0 : -p)
		};
	}
	var sign = (v) => v < 0 || Object.is(v, -0) ? "-" : "";
	/** Base::formatNumericValue with QuantityFormat::Fixed (NumericFormatting.cpp): ICU's DecimalFormat
	*  with `decimals` fraction digits and no grouping (OmitGroupSeparator), in the en_US_POSIX
	*  fallback locale. ICU rounds the double's shortest round-trip decimal digits, half to even —
	*  so 9.995 shows as 10.00 and 0.5 as 0 — and keeps the minus sign on negative zero and on
	*  negative numbers that round to zero. */
	function formatFixed(v, decimals) {
		if (!Number.isFinite(v)) return String(v);
		const { digits, exp } = shortestDigits(v);
		return sign(v) + pointed(roundHalfEven(digits, exp, decimals), decimals);
	}
	/** Quantity::toNumber: a std::stringstream at setprecision(precision), std::fixed for Fixed, std::scientific for
	*  Scientific and the default float format for Default — printf's %.*f, %.*e and %.*g, of the double's exact binary
	*  value, ties to even. */
	function toNumber(v, format, precision) {
		if (!Number.isFinite(v)) return Number.isNaN(v) ? "nan" : v < 0 ? "-inf" : "inf";
		const { digits, exp } = exactDigits(v);
		if (format === "Fixed") return sign(v) + pointed(roundHalfEven(digits, exp, precision), precision);
		if (format === "Scientific") {
			let n = roundHalfEven(digits, exp, precision - exp), X = exp;
			if (n.toString().length > precision + 1) {
				X = exp + 1;
				n /= 10n;
			}
			const m = n.toString().padStart(precision + 1, "0");
			return `${sign(v)}${m[0]}${precision ? "." + m.slice(1) : ""}e${X < 0 ? "-" : "+"}${String(Math.abs(X)).padStart(2, "0")}`;
		}
		const P = precision || 1;
		const n = roundHalfEven(digits, exp, P - 1 - exp);
		const X = n.toString().length > P ? exp + 1 : exp;
		const trim = (t) => t.includes(".") ? t.replace(/0+$/, "").replace(/\.$/, "") : t;
		if (P > X && X >= -4) return sign(v) + trim(pointed(roundHalfEven(digits, exp, P - 1 - X), P - 1 - X));
		const m = n.toString().slice(0, P);
		return `${sign(v)}${trim(m[0] + (P > 1 ? "." + m.slice(1) : ""))}e${X < 0 ? "-" : "+"}${String(Math.abs(X)).padStart(2, "0")}`;
	}
	/** UnitsSchema::translate: the quantity as the schema shows it, e.g. "12.50 mm" or "1.25 m".
	*  Returns the text, and the factor and unit it used. */
	function userString(q, schema = unitPrefs.schema, decimals = unitPrefs.decimals, denominator = unitPrefs.denominator) {
		const spec = SCHEMAS.find((s) => s.num === schema) ?? SCHEMAS[0];
		let factor = 1, unit = unitString(q.dims);
		const rows = spec.specs[typeString(q.dims)];
		if (rows) {
			const mag = Math.abs(q.value);
			const row = rows.find(([th]) => th * (1 - 1e-12) > mag || th === 0);
			if (!row) throw new QuantityError(`Suitable threshold not found. Schema: ${spec.name} value: ${q.value}`, "eval");
			if (row[2] === 0) {
				if (row[1] === "toFractional") return {
					text: toFractional(q.value, denominator),
					factor: 25.4,
					unit: "in"
				};
				if (row[1] === "toDMS") return {
					text: toDms(q.value),
					factor: 1,
					unit: "deg"
				};
			} else {
				factor = row[2];
				unit = row[1];
			}
		}
		return {
			text: `${formatFixed(q.value / factor, decimals)}${!unit || [
				"°",
				"″",
				"′",
				"\"",
				"'"
			].includes(unit) ? "" : " "}${unit}`,
			factor,
			unit
		};
	}
	//#endregion
	//#region src/expr-grammar.ts
	var TERMINALS = [
		"$end",
		"FUNC",
		"ONE",
		"NUM",
		"IDENTIFIER",
		"UNIT",
		"USUNIT",
		"INTEGER",
		"CONSTANT",
		"CELLADDRESS",
		"EQ",
		"NEQ",
		"LT",
		"GT",
		"GTE",
		"LTE",
		"STRING",
		"MINUSSIGN",
		"PROPERTY_REF",
		"DOCUMENT",
		"OBJECT",
		"EXPONENT",
		"'?'",
		"':'",
		"'+'",
		"'*'",
		"'/'",
		"'%'",
		"NUM_AND_UNIT",
		"'^'",
		"NEG",
		"POS",
		"'('",
		"')'",
		"','",
		"';'",
		"'.'",
		"'#'",
		"'['",
		"']'"
	];
	/** [left-hand side (index into NONTERMINALS), number of symbols on the right, the rule's text] */
	var RULES = [
		[
			0,
			2,
			"$accept: input $end"
		],
		[
			1,
			1,
			"input: exp"
		],
		[
			1,
			1,
			"input: unit_exp"
		],
		[
			2,
			2,
			"unit_num: num unit_exp %prec NUM_AND_UNIT"
		],
		[
			2,
			4,
			"unit_num: '(' exp ')' unit_exp %prec NUM_AND_UNIT"
		],
		[
			2,
			4,
			"unit_num: num us_building_unit num us_building_unit %prec NUM_AND_UNIT"
		],
		[
			3,
			1,
			"exp: num"
		],
		[
			3,
			1,
			"exp: unit_num"
		],
		[
			3,
			1,
			"exp: STRING"
		],
		[
			3,
			1,
			"exp: identifier"
		],
		[
			3,
			2,
			"exp: MINUSSIGN exp %prec NEG"
		],
		[
			3,
			2,
			"exp: '+' exp %prec POS"
		],
		[
			3,
			3,
			"exp: exp '+' exp"
		],
		[
			3,
			3,
			"exp: exp MINUSSIGN exp"
		],
		[
			3,
			3,
			"exp: exp '*' exp"
		],
		[
			3,
			3,
			"exp: exp '/' exp"
		],
		[
			3,
			3,
			"exp: exp '%' exp"
		],
		[
			3,
			3,
			"exp: exp '/' unit_exp"
		],
		[
			3,
			3,
			"exp: exp '^' exp"
		],
		[
			3,
			3,
			"exp: exp EQ exp"
		],
		[
			3,
			3,
			"exp: exp NEQ exp"
		],
		[
			3,
			3,
			"exp: exp LT exp"
		],
		[
			3,
			3,
			"exp: exp GT exp"
		],
		[
			3,
			3,
			"exp: exp GTE exp"
		],
		[
			3,
			3,
			"exp: exp LTE exp"
		],
		[
			3,
			1,
			"exp: indexable"
		],
		[
			3,
			3,
			"exp: FUNC args ')'"
		],
		[
			3,
			5,
			"exp: exp '?' exp ':' exp"
		],
		[
			3,
			3,
			"exp: '(' exp ')'"
		],
		[
			4,
			1,
			"num: ONE"
		],
		[
			4,
			1,
			"num: NUM"
		],
		[
			4,
			1,
			"num: INTEGER"
		],
		[
			4,
			1,
			"num: CONSTANT"
		],
		[
			5,
			1,
			"args: exp"
		],
		[
			5,
			1,
			"args: range"
		],
		[
			5,
			3,
			"args: args ',' exp"
		],
		[
			5,
			3,
			"args: args ';' exp"
		],
		[
			5,
			3,
			"args: args ',' range"
		],
		[
			5,
			3,
			"args: args ';' range"
		],
		[
			6,
			3,
			"range: id_or_cell ':' id_or_cell"
		],
		[
			7,
			1,
			"us_building_unit: USUNIT"
		],
		[
			8,
			1,
			"other_unit: UNIT"
		],
		[
			9,
			1,
			"unit_exp: other_unit"
		],
		[
			9,
			1,
			"unit_exp: us_building_unit"
		],
		[
			9,
			3,
			"unit_exp: unit_exp '/' unit_exp"
		],
		[
			9,
			3,
			"unit_exp: unit_exp '*' unit_exp"
		],
		[
			9,
			3,
			"unit_exp: unit_exp '^' integer"
		],
		[
			9,
			4,
			"unit_exp: unit_exp '^' MINUSSIGN integer"
		],
		[
			9,
			3,
			"unit_exp: '(' unit_exp ')'"
		],
		[
			10,
			1,
			"integer: INTEGER"
		],
		[
			10,
			1,
			"integer: ONE"
		],
		[
			11,
			1,
			"id_or_cell: IDENTIFIER"
		],
		[
			11,
			1,
			"id_or_cell: CELLADDRESS"
		],
		[
			12,
			1,
			"identifier: id_or_cell"
		],
		[
			12,
			1,
			"identifier: iden"
		],
		[
			13,
			4,
			"iden: '.' STRING '.' id_or_cell"
		],
		[
			13,
			2,
			"iden: '.' id_or_cell"
		],
		[
			13,
			5,
			"iden: object '.' STRING '.' id_or_cell"
		],
		[
			13,
			3,
			"iden: object '.' id_or_cell"
		],
		[
			13,
			5,
			"iden: document '#' object '.' id_or_cell"
		],
		[
			13,
			7,
			"iden: document '#' object '.' STRING '.' id_or_cell"
		],
		[
			13,
			3,
			"iden: iden '.' IDENTIFIER"
		],
		[
			14,
			3,
			"indexer: '[' exp ']'"
		],
		[
			14,
			4,
			"indexer: '[' exp ':' ']'"
		],
		[
			14,
			4,
			"indexer: '[' ':' exp ']'"
		],
		[
			14,
			5,
			"indexer: '[' ':' ':' exp ']'"
		],
		[
			14,
			5,
			"indexer: '[' exp ':' exp ']'"
		],
		[
			14,
			6,
			"indexer: '[' exp ':' ':' exp ']'"
		],
		[
			14,
			6,
			"indexer: '[' ':' exp ':' exp ']'"
		],
		[
			14,
			7,
			"indexer: '[' exp ':' exp ':' exp ']'"
		],
		[
			15,
			2,
			"indexable: identifier indexer"
		],
		[
			15,
			2,
			"indexable: indexable indexer"
		],
		[
			15,
			3,
			"indexable: indexable '.' IDENTIFIER"
		],
		[
			16,
			1,
			"document: STRING"
		],
		[
			16,
			1,
			"document: IDENTIFIER"
		],
		[
			17,
			1,
			"object: STRING"
		],
		[
			17,
			1,
			"object: id_or_cell"
		]
	];
	/** Per state: [shifts [token, state, ...], reductions [token, rule, ...], default rule or -1, gotos [nonterminal, state, ...], whether it reads the next token]. */
	var STATES = [
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				5,
				5,
				6,
				6,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				13,
				36,
				14
			],
			[],
			-1,
			[
				1,
				15,
				2,
				16,
				3,
				17,
				4,
				18,
				7,
				19,
				8,
				20,
				9,
				21,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				29,
				4,
				18,
				5,
				30,
				6,
				31,
				11,
				32,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			29,
			[],
			0
		],
		[
			[],
			[],
			30,
			[],
			0
		],
		[
			[],
			[37, 74],
			51,
			[],
			1
		],
		[
			[],
			[],
			41,
			[],
			0
		],
		[
			[],
			[],
			40,
			[],
			0
		],
		[
			[],
			[],
			31,
			[],
			0
		],
		[
			[],
			[],
			32,
			[],
			0
		],
		[
			[],
			[],
			52,
			[],
			0
		],
		[
			[],
			[
				36,
				75,
				37,
				73
			],
			8,
			[],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				33,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				34,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				5,
				5,
				6,
				6,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				13,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				35,
				4,
				18,
				7,
				19,
				8,
				20,
				9,
				36,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				4,
				37,
				9,
				9,
				16,
				38
			],
			[],
			-1,
			[11, 39],
			1
		],
		[
			[0, -1],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			7,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			1,
			[],
			1
		],
		[
			[
				5,
				5,
				6,
				6,
				32,
				54
			],
			[],
			6,
			[
				7,
				55,
				8,
				20,
				9,
				56
			],
			1
		],
		[
			[],
			[],
			43,
			[],
			0
		],
		[
			[],
			[],
			42,
			[],
			0
		],
		[
			[
				25,
				57,
				26,
				58,
				29,
				59
			],
			[],
			2,
			[],
			1
		],
		[
			[],
			[36, 76],
			53,
			[],
			1
		],
		[
			[38, 60],
			[],
			9,
			[14, 61],
			1
		],
		[
			[36, 62],
			[],
			54,
			[],
			1
		],
		[
			[
				36,
				63,
				38,
				60
			],
			[],
			25,
			[14, 64],
			1
		],
		[
			[37, 65],
			[],
			-1,
			[],
			1
		],
		[
			[36, 66],
			[],
			-1,
			[],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				35,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			33,
			[],
			1
		],
		[
			[
				33,
				67,
				34,
				68,
				35,
				69
			],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			34,
			[],
			0
		],
		[
			[23, 70],
			[36, 76],
			53,
			[],
			1
		],
		[
			[],
			[],
			10,
			[],
			0
		],
		[
			[],
			[],
			11,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				33,
				71
			],
			[],
			-1,
			[],
			1
		],
		[
			[
				25,
				57,
				26,
				58,
				29,
				59,
				33,
				72
			],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			51,
			[],
			0
		],
		[
			[36, 73],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			56,
			[],
			0
		],
		[
			[],
			[],
			-1,
			[],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				74,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				75,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				76,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				77,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				78,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				79,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				80,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				81,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				82,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				83,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				5,
				5,
				6,
				6,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				13,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				84,
				4,
				18,
				7,
				19,
				8,
				20,
				9,
				85,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				86,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				87,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				5,
				5,
				6,
				6,
				32,
				54
			],
			[],
			-1,
			[
				7,
				19,
				8,
				20,
				9,
				36
			],
			1
		],
		[
			[
				2,
				2,
				3,
				3,
				7,
				7,
				8,
				8
			],
			[],
			43,
			[4, 88],
			1
		],
		[
			[29, 59],
			[],
			3,
			[],
			1
		],
		[
			[
				5,
				5,
				6,
				6,
				32,
				54
			],
			[],
			-1,
			[
				7,
				19,
				8,
				20,
				9,
				89
			],
			1
		],
		[
			[
				5,
				5,
				6,
				6,
				32,
				54
			],
			[],
			-1,
			[
				7,
				19,
				8,
				20,
				9,
				90
			],
			1
		],
		[
			[
				2,
				91,
				7,
				92,
				17,
				93
			],
			[],
			-1,
			[10, 94],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				23,
				95,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				96,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			70,
			[],
			0
		],
		[
			[4, 97],
			[],
			-1,
			[],
			1
		],
		[
			[4, 98],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			71,
			[],
			0
		],
		[
			[
				4,
				37,
				9,
				9,
				16,
				99
			],
			[],
			-1,
			[
				11,
				100,
				17,
				101
			],
			1
		],
		[
			[
				4,
				37,
				9,
				9,
				16,
				102
			],
			[],
			-1,
			[11, 103],
			1
		],
		[
			[],
			[],
			26,
			[],
			0
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				104,
				4,
				18,
				6,
				105,
				11,
				32,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				106,
				4,
				18,
				6,
				107,
				11,
				32,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				4,
				37,
				9,
				9
			],
			[],
			-1,
			[11, 108],
			1
		],
		[
			[
				5,
				5,
				6,
				6,
				32,
				54
			],
			[],
			28,
			[
				7,
				19,
				8,
				20,
				9,
				109
			],
			1
		],
		[
			[],
			[],
			48,
			[],
			0
		],
		[
			[
				4,
				37,
				9,
				9
			],
			[],
			-1,
			[11, 110],
			1
		],
		[
			[
				17,
				47,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			19,
			[],
			1
		],
		[
			[
				17,
				47,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			20,
			[],
			1
		],
		[
			[
				17,
				47,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			21,
			[],
			1
		],
		[
			[
				17,
				47,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			22,
			[],
			1
		],
		[
			[
				17,
				47,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			23,
			[],
			1
		],
		[
			[
				17,
				47,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			24,
			[],
			1
		],
		[
			[
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			13,
			[],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				23,
				111,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			-1,
			[],
			1
		],
		[
			[
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			12,
			[],
			1
		],
		[
			[29, 53],
			[],
			14,
			[],
			1
		],
		[
			[29, 53],
			[],
			15,
			[],
			1
		],
		[
			[29, 59],
			[],
			17,
			[],
			1
		],
		[
			[29, 53],
			[],
			16,
			[],
			1
		],
		[
			[],
			[],
			18,
			[],
			0
		],
		[
			[6, 6],
			[],
			-1,
			[7, 112],
			1
		],
		[
			[29, 59],
			[],
			45,
			[],
			1
		],
		[
			[29, 59],
			[],
			44,
			[],
			1
		],
		[
			[],
			[],
			50,
			[],
			0
		],
		[
			[],
			[],
			49,
			[],
			0
		],
		[
			[
				2,
				91,
				7,
				92
			],
			[],
			-1,
			[10, 113],
			1
		],
		[
			[],
			[],
			46,
			[],
			0
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				23,
				114,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				115,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				23,
				116,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				117
			],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			61,
			[],
			0
		],
		[
			[],
			[],
			72,
			[],
			0
		],
		[
			[],
			[],
			75,
			[],
			0
		],
		[
			[],
			[],
			76,
			[],
			0
		],
		[
			[36, 118],
			[],
			-1,
			[],
			1
		],
		[
			[36, 119],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			58,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			35,
			[],
			1
		],
		[
			[],
			[],
			37,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			36,
			[],
			1
		],
		[
			[],
			[],
			38,
			[],
			0
		],
		[
			[],
			[],
			39,
			[],
			0
		],
		[
			[29, 59],
			[],
			4,
			[],
			1
		],
		[
			[],
			[],
			55,
			[],
			0
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				120,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			5,
			[],
			0
		],
		[
			[],
			[],
			47,
			[],
			0
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				121,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				23,
				122,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				123
			],
			[],
			-1,
			[],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				23,
				124,
				24,
				12,
				32,
				28,
				36,
				14,
				39,
				125
			],
			[],
			-1,
			[
				2,
				16,
				3,
				126,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			62,
			[],
			0
		],
		[
			[
				4,
				37,
				9,
				9,
				16,
				127
			],
			[],
			-1,
			[11, 128],
			1
		],
		[
			[
				4,
				37,
				9,
				9
			],
			[],
			-1,
			[11, 129],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53
			],
			[],
			27,
			[],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				130
			],
			[],
			-1,
			[],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				131,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			64,
			[],
			0
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				132,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			63,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				23,
				133,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				134
			],
			[],
			-1,
			[],
			1
		],
		[
			[36, 135],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			59,
			[],
			0
		],
		[
			[],
			[],
			57,
			[],
			0
		],
		[
			[],
			[],
			65,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				136
			],
			[],
			-1,
			[],
			1
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				137
			],
			[],
			-1,
			[],
			1
		],
		[
			[
				1,
				1,
				2,
				2,
				3,
				3,
				4,
				4,
				7,
				7,
				8,
				8,
				9,
				9,
				16,
				10,
				17,
				11,
				24,
				12,
				32,
				28,
				36,
				14
			],
			[],
			-1,
			[
				2,
				16,
				3,
				138,
				4,
				18,
				11,
				22,
				12,
				23,
				13,
				24,
				15,
				25,
				16,
				26,
				17,
				27
			],
			1
		],
		[
			[],
			[],
			66,
			[],
			0
		],
		[
			[
				4,
				37,
				9,
				9
			],
			[],
			-1,
			[11, 139],
			1
		],
		[
			[],
			[],
			68,
			[],
			0
		],
		[
			[],
			[],
			67,
			[],
			0
		],
		[
			[
				10,
				41,
				11,
				42,
				12,
				43,
				13,
				44,
				14,
				45,
				15,
				46,
				17,
				47,
				22,
				48,
				24,
				49,
				25,
				50,
				26,
				51,
				27,
				52,
				29,
				53,
				39,
				140
			],
			[],
			-1,
			[],
			1
		],
		[
			[],
			[],
			60,
			[],
			0
		],
		[
			[],
			[],
			69,
			[],
			0
		]
	];
	//#endregion
	//#region src/expr-py.ts
	var ZERO$1 = [
		0,
		0,
		0,
		0,
		0,
		0,
		0,
		0
	];
	var ANGLE = [
		0,
		0,
		0,
		0,
		0,
		0,
		0,
		1
	];
	/** An exception as Python reports it: its class name and message are what evalExpression raises. */
	var PyError = class extends QuantityError {
		etype;
		raw;
		/** `raw`: a Base exception that went through Python's C API without becoming a Python exception, so that calc() does not
		*  add the "in expression:" line to it (a Quantity comparison between different units is one). */
		constructor(message, etype, kind = "eval", raw = false) {
			super(message, kind);
			this.etype = etype;
			this.raw = raw;
			this.name = etype;
		}
	};
	/** Base::UnitsMismatchError (Python's ArithmeticError). */
	var mismatch = (message) => new PyError(message, "ArithmeticError", "mismatch");
	var typeError = (message) => new PyError(message, "TypeError");
	/** The SystemError Python raises when a call returned a result with an exception set: its message names the call. */
	var systemError = () => new PyError("<built-in method evalExpression of FeaturePython object at 0x0> returned a result with an exception set", "SystemError", "eval", true);
	/** Where FreeCAD does something its authors cannot have meant; off here, and on for the differential test
	*  (scripts/exprdiff.py) so that every other answer can be compared. */
	var QUIRKS = { 
	/** essentiallyInteger (App/Expression.cpp) casts an integral double above INT_MAX to int, so on x86 the Python int that comes
	*  out of 3000000000, 1e10 or 2^31 as a number is -2147483648. */
int32Cast: false };
	var int = (v) => ({
		t: "int",
		v: BigInt(v)
	});
	var float = (v) => ({
		t: "float",
		v
	});
	var bool = (v) => ({
		t: "bool",
		v
	});
	var str = (v) => ({
		t: "str",
		v
	});
	var none = { t: "none" };
	/** tp_name, as the messages spell it. */
	function typeName(a) {
		return a.t === "qty" ? "Base.Quantity" : a.t === "none" ? "NoneType" : a.t === "obj" ? a.type : a.t === "vector" ? "Base.Vector" : a.t;
	}
	var isReal = (a) => a.t === "int" || a.t === "float" || a.t === "bool";
	/** PyNumber_Check (a Vector passes it, as it sets the nb_int and nb_float slots). */
	var isNumeric = (a) => isReal(a) || a.t === "complex" || a.t === "qty" || a.t === "vector";
	var isIntLike = (a) => a.t === "int" || a.t === "bool";
	var bigOf = (a) => a.t === "int" ? a.v : a.t === "bool" ? a.v ? 1n : 0n : 0n;
	var isDimless = (d) => d.every((x) => x === 0);
	var sameDims = (a, b) => a.every((x, i) => x === b[i]);
	/** Unit's checkRange(): every exponent within [-8, 7]. */
	function checkRange(d) {
		for (const e of d) {
			if (e >= 8) throw new PyError("Unit exponent overflow", "OverflowError");
			if (e < -8) throw new PyError("Unit exponent underflow", "ArithmeticError");
		}
		return d;
	}
	var unitMul = (a, b) => checkRange(a.map((x, i) => x + b[i]));
	var unitDiv = (a, b) => checkRange(a.map((x, i) => x - b[i]));
	/** static_cast<int8_t>(double) as x86 does it: through a 32-bit integer, whose low byte is kept. */
	function toInt8(x) {
		if (!Number.isFinite(x)) return 0;
		const t = Math.trunc(x);
		if (t > 2147483647 || t < -2147483648) return 0;
		return t << 24 >> 24;
	}
	/** Unit::pow(double). */
	function unitPow(a, exp) {
		return checkRange(a.map((val) => {
			const num = val * exp;
			if (Math.abs(Math.round(num) - num) >= Number.EPSILON) throw mismatch("pow() of unit not possible");
			return toInt8(val * exp);
		}));
	}
	/** Unit::root(n) (sqrt() and cbrt()). */
	function unitRoot(a, n) {
		return checkRange(a.map((val) => {
			if (val % n !== 0) throw mismatch("unit values must be divisible by root");
			return val / n;
		}));
	}
	var qAdd = (a, b) => {
		if (!sameDims(a.dims, b.dims)) throw mismatch("Quantity::operator +(): Unit mismatch in plus operation");
		return {
			value: a.value + b.value,
			dims: a.dims
		};
	};
	var qSub = (a, b) => {
		if (!sameDims(a.dims, b.dims)) throw mismatch("Quantity::operator -(): Unit mismatch in minus operation");
		return {
			value: a.value - b.value,
			dims: a.dims
		};
	};
	var qMul = (a, b) => ({
		value: a.value * b.value,
		dims: unitMul(a.dims, b.dims)
	});
	var qDiv = (a, b) => ({
		value: a.value / b.value,
		dims: unitDiv(a.dims, b.dims)
	});
	/** Quantity::pow(const Quantity&): the unit is raised to the exponent cast to signed char. */
	function qPowQ(a, b) {
		if (!isDimless(b.dims)) throw mismatch("Quantity::pow(): exponent must not have a unit");
		return {
			value: cpow(a.value, b.value),
			dims: unitPow(a.dims, toInt8(b.value))
		};
	}
	/** Quantity::pow(double). */
	var qPowD = (a, exp) => ({
		value: cpow(a.value, exp),
		dims: unitPow(a.dims, exp)
	});
	var qLt = (a, b) => {
		if (!sameDims(a.dims, b.dims)) throw new PyError("Quantity::operator <(): quantities need to have same unit to compare", "ArithmeticError", "mismatch", true);
		return a.value < b.value;
	};
	/** Quantity::operator< and operator>, which the min and max collectors call directly. */
	var qLess = qLt;
	var qGreater = (a, b) => {
		if (!sameDims(a.dims, b.dims)) throw new PyError("Quantity::operator >(): quantities need to have same unit to compare", "ArithmeticError", "mismatch", true);
		return a.value > b.value;
	};
	/** Quantity::operator+= (the sum and average collectors). */
	var qAddAssign = (a, b) => {
		if (!sameDims(a.dims, b.dims)) throw mismatch("Quantity::operator +=(): Unit mismatch in plus operation");
		return {
			value: a.value + b.value,
			dims: a.dims
		};
	};
	var qEq = (a, b) => a.value === b.value && sameDims(a.dims, b.dims);
	var overflow = (message) => new PyError(message, "OverflowError");
	/** float(int): round to nearest, an OverflowError when it does not fit. */
	function floatOfInt(v) {
		const x = Number(v);
		if (!Number.isFinite(x)) throw overflow("int too large to convert to float");
		return x;
	}
	/** PyFloat_AsDouble on an int too big for a double fails with an OverflowError, which the C++ callers do not look at: the call
	*  goes on and Python ends it with a SystemError. */
	function asDoubleOrSystemError(a) {
		try {
			return realToFloat(a);
		} catch {
			throw systemError();
		}
	}
	var realToFloat = (a) => a.t === "float" ? a.v : floatOfInt(bigOf(a));
	/** int / int, rounded once, as Python's long_true_divide rounds it. */
	function intTrueDiv(a, b) {
		if (b === 0n) throw new PyError("division by zero", "ZeroDivisionError");
		const lim = 1n << 53n;
		if (a > -lim && a < lim && b > -lim && b < lim) return Number(a) / Number(b);
		const neg = a < 0n !== b < 0n;
		const x = a < 0n ? -a : a, y = b < 0n ? -b : b;
		if (x === 0n) return neg ? -0 : 0;
		const bits = (n) => n.toString(2).length;
		const shift = 66 - (bits(x) - bits(y));
		const num = shift >= 0 ? x << BigInt(shift) : x, den = shift >= 0 ? y : y << BigInt(-shift);
		let q = num / den;
		if (num % den !== 0n) q |= 1n;
		let r = Number(q);
		const s = shift;
		const half = Math.trunc(s / 2);
		r = r * Math.pow(2, -half) * Math.pow(2, -(s - half));
		if (!Number.isFinite(r)) throw overflow("integer division result too large for a float");
		return neg ? -r : r;
	}
	/** floor division remainder: the sign of the divisor. */
	function intMod(a, b) {
		if (b === 0n) throw new PyError("integer modulo by zero", "ZeroDivisionError");
		let r = a % b;
		if (r !== 0n && r < 0n !== b < 0n) r += b;
		return r;
	}
	function floatMod(vx, wx) {
		if (wx === 0) throw new PyError("float modulo by zero", "ZeroDivisionError");
		let mod = vx % wx;
		if (mod !== 0) {
			if (wx < 0 !== mod < 0) mod += wx;
		} else mod = wx < 0 || Object.is(wx, -0) ? -0 : 0;
		return mod;
	}
	/** x ** n for a whole n, rounded once: the double x is m * 2^e with m a whole number, so m ** n is exact in BigInt. null if the
	*  answer is not a normal double. */
	function exactPow(x, n) {
		const view = /* @__PURE__ */ new DataView(/* @__PURE__ */ new ArrayBuffer(8));
		view.setFloat64(0, x);
		const hi = view.getUint32(0), lo = view.getUint32(4), biased = hi >>> 20 & 2047;
		if (biased === 0) return null;
		let m = BigInt(hi & 1048575) << 32n | BigInt(lo);
		m |= 1n << 52n;
		if (hi >>> 31) m = -m;
		const e = biased - 1075;
		const k = Math.abs(n);
		const mk = m ** BigInt(k);
		const E = e * k;
		try {
			const r = n >= 0 ? Number(mk) * Math.pow(2, E) : E >= 0 ? intTrueDiv(1n, mk << BigInt(E)) : intTrueDiv(1n << BigInt(-E), mk);
			return Number.isFinite(r) && Math.abs(r) >= 22250738585072014e-324 ? r : null;
		} catch {
			return null;
		}
	}
	/** C's pow(): the special cases of C99 (JavaScript's Math.pow differs on 1 and -1 to an infinite or NaN power), and a whole power
	*  of a double rounded once, where V8's pow can be a unit in the last place off (10 ** -5). */
	function cpow(x, y) {
		if (x === 1 || y === 0) return 1;
		if (x === -1 && (y === Infinity || y === -Infinity)) return 1;
		if (Number.isInteger(y) && Math.abs(y) <= 128 && Number.isFinite(x) && x !== 0) {
			const r = exactPow(x, y);
			if (r !== null) return r;
		}
		return Math.pow(x, y);
	}
	var isOddInteger = (x) => Number.isInteger(x) && Math.abs(x % 2) === 1;
	/** float_pow (Objects/floatobject.c): the special cases are Python's, the rest is libm's pow(). */
	function floatPow(iv, iw) {
		if (iw === 0) return float(1);
		if (Number.isNaN(iv)) return float(iv);
		if (Number.isNaN(iw)) return float(iv === 1 ? 1 : iw);
		if (!Number.isFinite(iw)) {
			iv = Math.abs(iv);
			if (iv === 1) return float(1);
			return float(iw > 0 === iv > 1 ? Math.abs(iw) : 0);
		}
		if (!Number.isFinite(iv)) {
			const odd = isOddInteger(iw);
			if (iw > 0) return float(odd ? iv : Math.abs(iv));
			return float(odd ? iv < 0 ? -0 : 0 : 0);
		}
		if (iv === 0) {
			const odd = isOddInteger(iw);
			if (iw < 0) throw new PyError("0.0 cannot be raised to a negative power", "ZeroDivisionError");
			return float(odd ? iv : 0);
		}
		let negate = false;
		if (iv < 0) {
			if (iw !== Math.floor(iw)) return complexPow({
				re: iv,
				im: 0
			}, {
				re: iw,
				im: 0
			});
			iv = -iv;
			negate = isOddInteger(iw);
		}
		if (iv === 1) return float(negate ? -1 : 1);
		let ix = cpow(iv, iw);
		if (!Number.isFinite(ix)) throw overflow("(34, 'Result too large')");
		if (negate) ix = -ix;
		return float(ix);
	}
	/** _Py_c_pow for a complex or real base and exponent. */
	function complexPow(a, b) {
		if (b.re === 0 && b.im === 0) return {
			t: "complex",
			re: 1,
			im: 0
		};
		if (a.re === 0 && a.im === 0) {
			if (b.im !== 0 || b.re < 0) throw new PyError("0.0 to a negative or complex power", "ZeroDivisionError");
			return {
				t: "complex",
				re: 0,
				im: 0
			};
		}
		const vabs = Math.hypot(a.re, a.im);
		let len = cpow(vabs, b.re);
		const at = Math.atan2(a.im, a.re);
		let phase = at * b.re;
		if (b.im !== 0) {
			len /= Math.exp(at * b.im);
			phase += b.im * Math.log(vabs);
		}
		const re = len * Math.cos(phase), im = len * Math.sin(phase);
		if (!Number.isFinite(re) || !Number.isFinite(im)) {
			if (Number.isFinite(a.re) && Number.isFinite(a.im) && Number.isFinite(b.re) && Number.isFinite(b.im)) throw overflow("complex exponentiation");
		}
		return {
			t: "complex",
			re,
			im
		};
	}
	var toC = (a) => a.t === "complex" ? a : {
		re: realToFloat(a),
		im: 0
	};
	/** The longest string, list or tuple, and the widest % field, an expression may make here: Python would build a longer one
	*  (or run out of memory), a browser tab would freeze or crash first. Past it: a MemoryError, as for the int powers below. */
	var MAX_LENGTH = 1e7;
	var fits = (length) => {
		if (length > MAX_LENGTH) throw new PyError("result too large to compute here", "MemoryError");
		return length;
	};
	var sized = (length, make) => (fits(length), make());
	/** int ** int: exact for a non-negative exponent, else the float answer. */
	function intPow(a, b) {
		if (b < 0n) return floatPow(floatOfInt(a), floatOfInt(b));
		if (a === 0n || a === 1n || b === 0n) return {
			t: "int",
			v: b === 0n ? 1n : a
		};
		if (a === -1n) return {
			t: "int",
			v: b % 2n === 0n ? 1n : -1n
		};
		if (BigInt((a < 0n ? -a : a).toString(2).length) * b > 4000000n) throw new PyError("integer power too large to compute here", "MemoryError");
		return {
			t: "int",
			v: a ** b
		};
	}
	/** pyFromQuantity (App/Expression.cpp): a quantity with a unit stays one; a plain number becomes a Python int when it is a whole
	*  number (essentiallyInteger), else a float. */
	function fromQuantity(q) {
		if (!isDimless(q.dims)) return {
			t: "qty",
			q
		};
		const v = q.value;
		if (Number.isFinite(v) && Number.isInteger(v)) {
			if (v < 0) {
				if (v >= -2147483648) return int(v);
				if (v >= -0x8000000000000000) return int(BigInt(v));
			} else if (v <= 2147483647) return int(v);
			else if (v <= 0x8000000000000000) return QUIRKS.int32Cast ? int(-2147483648) : int(BigInt(v));
		}
		return float(v);
	}
	/** pyToQuantity (App/Expression.cpp): a Quantity, a float or an int; null for anything else. A bool is an int to Python. */
	function toQuantity(a) {
		if (a.t === "qty") return a.q;
		if (a.t === "float") return {
			value: a.v,
			dims: ZERO$1
		};
		if (isIntLike(a)) {
			const v = bigOf(a);
			if (v > 9223372036854775807n || v < -9223372036854775808n) throw new PyError("Python int too large to convert to C long", "OverflowError");
			return {
				value: Number(v),
				dims: ZERO$1
			};
		}
		return null;
	}
	/** PyObject_IsTrue. A Quantity is true unless its value is zero (QuantityPy::number_nonzero_handler). */
	function truth(a) {
		switch (a.t) {
			case "int": return a.v !== 0n;
			case "float": return a.v !== 0;
			case "bool": return a.v;
			case "str": return a.v.length > 0;
			case "none": return false;
			case "qty": return a.q.value !== 0;
			case "complex": return a.re !== 0 || a.im !== 0;
			case "list":
			case "tuple": return a.v.length > 0;
			default: return true;
		}
	}
	var SYM = {
		eq: "==",
		ne: "!=",
		lt: "<",
		le: "<=",
		gt: ">",
		ge: ">="
	};
	function relNum(a, b, op) {
		switch (op) {
			case "eq": return typeof a === typeof b ? a === b : a == b;
			case "ne": return !relNum(a, b, "eq");
			case "lt": return a < b;
			case "le": return a <= b;
			case "gt": return a > b;
			case "ge": return a >= b;
		}
	}
	var numOf = (a) => a.t === "float" ? a.v : bigOf(a);
	function cmpStr(a, b, op) {
		if (op === "eq") return a === b;
		if (op === "ne") return a !== b;
		const x = Array.from(a, (c) => c.codePointAt(0)), y = Array.from(b, (c) => c.codePointAt(0));
		let i = 0;
		while (i < x.length && i < y.length && x[i] === y[i]) i++;
		const c = i < x.length && i < y.length ? x[i] - y[i] : x.length - y.length;
		return op === "lt" ? c < 0 : op === "le" ? c <= 0 : op === "gt" ? c > 0 : c >= 0;
	}
	/** list and tuple: the first pair of items that differ decides (list_richcompare). */
	function cmpSeq(a, b, op) {
		if (a.length !== b.length && (op === "eq" || op === "ne")) return op === "ne";
		let i = 0;
		while (i < a.length && i < b.length && compare(a[i], b[i], "eq")) i++;
		if (i >= a.length || i >= b.length) return relNum(a.length, b.length, op);
		if (op === "eq") return false;
		if (op === "ne") return true;
		return compare(a[i], b[i], op);
	}
	/** PyObject_RichCompareBool(a, b, op) with FreeCAD's types: Base/QuantityPyImp.cpp richCompare for a Quantity, which compares
	*  two quantities by value and unit, a Quantity and any other number by value alone. */
	function compare(a, b, op) {
		if (a.t === "qty" && b.t === "qty") {
			const u1 = a.q, u2 = b.q;
			switch (op) {
				case "ne": return !qEq(u1, u2);
				case "lt": return qLt(u1, u2);
				case "le": return qLt(u1, u2) || qEq(u1, u2);
				case "gt": return !qLt(u1, u2) && !qEq(u1, u2);
				case "ge": return !qLt(u1, u2);
				case "eq": return qEq(u1, u2);
			}
		}
		if (a.t === "vector" && b.t === "vector") {
			if (op !== "eq" && op !== "ne") throw typeError("no ordering relation is defined for Vector");
			const eq = a.v.every((x, i) => Math.abs(x - b.v[i]) <= Number.EPSILON);
			return op === "eq" ? eq : !eq;
		}
		if (a.t === "qty" && isNumeric(b) || b.t === "qty" && isNumeric(a)) {
			const dbl = (x) => {
				if (x.t === "qty") return x.q.value;
				if (x.t === "complex") throw typeError("must be real number, not complex");
				if (x.t === "vector") throw systemError();
				return asDoubleOrSystemError(x);
			};
			return relNum(dbl(a), dbl(b), op);
		}
		if (isReal(a) && isReal(b)) return relNum(numOf(a), numOf(b), op);
		if (a.t === "complex" || b.t === "complex") {
			if ((a.t === "complex" || isReal(a)) && (b.t === "complex" || isReal(b))) {
				if (op !== "eq" && op !== "ne") throw typeError(`'${SYM[op]}' not supported between instances of '${typeName(a)}' and '${typeName(b)}'`);
				const x = toC(a), y = toC(b);
				const eq = x.re === y.re && x.im === y.im;
				return op === "eq" ? eq : !eq;
			}
		}
		if (a.t === "str" && b.t === "str") return cmpStr(a.v, b.v, op);
		if (a.t === "list" && b.t === "list") return cmpSeq(a.v, b.v, op);
		if (a.t === "tuple" && b.t === "tuple") return cmpSeq(a.v, b.v, op);
		if (a.t === "none" && b.t === "none") {
			if (op === "eq") return true;
			if (op === "ne") return false;
		}
		if (a.t === "obj" && b.t === "obj" && (op === "eq" || op === "ne")) return a.str === b.str === (op === "eq");
		if (op === "eq") return false;
		if (op === "ne") return true;
		throw typeError(`'${SYM[op]}' not supported between instances of '${typeName(a)}' and '${typeName(b)}'`);
	}
	/** calc() runs PyNumber_InPlaceRemainder for "%", so its message says "%=". */
	var SYMBOL = {
		add: "+",
		sub: "-",
		mul: "*",
		div: "/",
		mod: "%=",
		pow: "** or pow()"
	};
	/** Base::QuantityPy's pyToQuantity (QuantityPyImp.cpp): a Quantity, a float or an int, else a TypeError. */
	function qOperand(a) {
		if (a.t === "qty") return a.q;
		const q = isReal(a) ? toQuantity(a) : null;
		if (!q) throw typeError(`Cannot convert ${typeName(a)} to Quantity`);
		return q;
	}
	/** QuantityPy's number_*_handler, which Python calls when either operand is a Quantity (the left one first). */
	function quantityOp(op, a, b) {
		switch (op) {
			case "add":
			case "sub":
			case "mul":
			case "div": {
				const x = qOperand(a), y = qOperand(b);
				return {
					t: "qty",
					q: op === "add" ? qAdd(x, y) : op === "sub" ? qSub(x, y) : op === "mul" ? qMul(x, y) : qDiv(x, y)
				};
			}
			case "mod": {
				if (a.t !== "qty") throw typeError("First arg must be Quantity");
				let d2;
				if (b.t === "qty") d2 = b.q.value;
				else if (b.t === "float") d2 = b.v;
				else if (isIntLike(b)) d2 = Number(toQuantity(b).value);
				else throw typeError("Expected quantity or number");
				return {
					t: "qty",
					q: {
						value: floatMod(a.q.value, d2),
						dims: a.q.dims
					}
				};
			}
			case "pow":
				if (a.t !== "qty") throw typeError("First arg must be Quantity");
				if (b.t === "qty") return {
					t: "qty",
					q: qPowQ(a.q, b.q)
				};
				if (b.t === "float") return {
					t: "qty",
					q: qPowD(a.q, b.v)
				};
				if (isIntLike(b)) return {
					t: "qty",
					q: qPowD(a.q, toQuantity(b).value)
				};
				throw typeError("Expected quantity or number");
		}
	}
	var vecSub = (a, b) => [
		a[0] - b[0],
		a[1] - b[1],
		a[2] - b[2]
	];
	var vecAdd = (a, b) => [
		a[0] + b[0],
		a[1] + b[1],
		a[2] + b[2]
	];
	var vecScale = (a, f) => [
		a[0] * f,
		a[1] * f,
		a[2] * f
	];
	var vecDot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
	var vecCross = (a, b) => [
		a[1] * b[2] - a[2] * b[1],
		a[2] * b[0] - a[0] * b[2],
		a[0] * b[1] - a[1] * b[0]
	];
	var vecLength = (a) => Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
	var vecSqr = (a) => a[0] * a[0] + a[1] * a[1] + a[2] * a[2];
	var vector = (v) => ({
		t: "vector",
		v
	});
	/** VectorPy's number handlers (Base/VectorPyImp.cpp), which Python calls when either operand is a Vector. */
	function vectorOp(op, a, b) {
		const tn = (x) => typeName(x);
		const scalar = (x) => {
			if (x.t === "qty") return x.q.value;
			if (x.t === "complex") throw typeError("must be real number, not complex");
			return asDoubleOrSystemError(x);
		};
		switch (op) {
			case "add":
			case "sub":
				if (a.t !== "vector") throw typeError("First arg must be Vector");
				if (b.t !== "vector") throw typeError("Second arg must be Vector");
				return vector(op === "add" ? vecAdd(a.v, b.v) : vecSub(a.v, b.v));
			case "mul":
				if (a.t === "vector") {
					if (b.t === "vector") return float(vecDot(a.v, b.v));
					if (isNumeric(b)) return vector(vecScale(a.v, scalar(b)));
					throw typeError("A Vector can only be multiplied by Vector or number");
				}
				if (b.t === "vector" && isNumeric(a)) return vector(vecScale(b.v, scalar(a)));
				if (b.t === "vector") throw typeError("A Vector can only be multiplied by Vector or number");
				throw typeError("First or second arg must be Vector");
			case "div":
				if (a.t === "vector" && isNumeric(b)) {
					if (b.t === "vector") throw typeError(`unsupported operand type(s) for /: '${tn(a)}' and '${tn(b)}'`);
					const d = scalar(b);
					if (d === 0) throw new PyError(`'${tn(a)}' division by zero`, "ZeroDivisionError");
					return vector([
						a.v[0] / d,
						a.v[1] / d,
						a.v[2] / d
					]);
				}
				throw typeError(`unsupported operand type(s) for /: '${tn(a)}' and '${tn(b)}'`);
			case "mod":
				if (a.t === "vector" && b.t === "vector") return vector(vecCross(a.v, b.v));
				throw typeError(`unsupported operand type(s) for %: '${tn(a)}' and '${tn(b)}'`);
			case "pow": throw typeError(`unsupported operand type(s) for ** or pow(): '${tn(a)}' and '${tn(b)}'`);
		}
	}
	function seqRepeat(seq, n) {
		if (!isIntLike(n)) throw typeError(`can't multiply sequence by non-int of type '${typeName(n)}'`);
		const count = bigOf(n);
		if (count > 1n << 31n) throw new PyError("", "MemoryError");
		const k = Number(count < 0n ? 0n : count);
		if (seq.t === "str") return str(sized(seq.v.length * k, () => seq.v.repeat(k)));
		const items = seq.v;
		return {
			t: seq.t,
			v: sized(items.length * k, () => Array.from({ length: k }, () => items).flat())
		};
	}
	var isSeq = (a) => a.t === "str" || a.t === "list" || a.t === "tuple";
	/** PyNumber_Add and its kin, for FreeCAD's operand types. */
	function binary(op, a, b) {
		if (op === "mod" && a.t === "str") return str(percentFormat(a.v, b));
		if (a.t === "qty") return quantityOp(op, a, b);
		if (a.t === "vector" || b.t === "vector") return vectorOp(op, a, b);
		if (b.t === "qty") return quantityOp(op, a, b);
		const bothInt = isIntLike(a) && isIntLike(b);
		if (isReal(a) && isReal(b) || (a.t === "complex" || isReal(a)) && (b.t === "complex" || isReal(b))) {
			if (a.t === "complex" || b.t === "complex") return complexOp(op, a, b);
			switch (op) {
				case "add": return bothInt ? {
					t: "int",
					v: bigOf(a) + bigOf(b)
				} : float(realToFloat(a) + realToFloat(b));
				case "sub": return bothInt ? {
					t: "int",
					v: bigOf(a) - bigOf(b)
				} : float(realToFloat(a) - realToFloat(b));
				case "mul": return bothInt ? {
					t: "int",
					v: bigOf(a) * bigOf(b)
				} : float(realToFloat(a) * realToFloat(b));
				case "div": {
					if (bothInt) return float(intTrueDiv(bigOf(a), bigOf(b)));
					const x = realToFloat(a), y = realToFloat(b);
					if (y === 0) throw new PyError("float division by zero", "ZeroDivisionError");
					return float(x / y);
				}
				case "mod": return bothInt ? {
					t: "int",
					v: intMod(bigOf(a), bigOf(b))
				} : float(floatMod(realToFloat(a), realToFloat(b)));
				case "pow": return bothInt ? intPow(bigOf(a), bigOf(b)) : floatPow(realToFloat(a), realToFloat(b));
			}
		}
		switch (op) {
			case "add":
				if (a.t === "str" && b.t === "str") return str(sized(a.v.length + b.v.length, () => a.v + b.v));
				if (a.t === "list" && b.t === "list") return {
					t: "list",
					v: sized(a.v.length + b.v.length, () => [...a.v, ...b.v])
				};
				if (a.t === "tuple" && b.t === "tuple") return {
					t: "tuple",
					v: sized(a.v.length + b.v.length, () => [...a.v, ...b.v])
				};
				if (a.t === "str") throw typeError(`can only concatenate str (not "${typeName(b)}") to str`);
				if (a.t === "list") throw typeError(`can only concatenate list (not "${typeName(b)}") to list`);
				if (a.t === "tuple") throw typeError(`can only concatenate tuple (not "${typeName(b)}") to tuple`);
				break;
			case "mul":
				if (isSeq(a) && !isSeq(b)) return seqRepeat(a, b);
				if (isSeq(b) && !isSeq(a)) return seqRepeat(b, a);
				if (isSeq(a) && isSeq(b)) throw typeError(`can't multiply sequence by non-int of type '${typeName(b)}'`);
		}
		throw typeError(`unsupported operand type(s) for ${SYMBOL[op]}: '${typeName(a)}' and '${typeName(b)}'`);
	}
	function complexOp(op, a, b) {
		if (op === "mod") throw typeError(`unsupported operand type(s) for %=: '${typeName(a)}' and '${typeName(b)}'`);
		const x = toC(a), y = toC(b);
		switch (op) {
			case "add": return {
				t: "complex",
				re: x.re + y.re,
				im: x.im + y.im
			};
			case "sub": return {
				t: "complex",
				re: x.re - y.re,
				im: x.im - y.im
			};
			case "mul": return {
				t: "complex",
				re: x.re * y.re - x.im * y.im,
				im: x.re * y.im + x.im * y.re
			};
			case "div": {
				if (y.re * y.re + y.im * y.im === 0) throw new PyError("division by zero", "ZeroDivisionError");
				const abs_breal = Math.abs(y.re);
				if (abs_breal >= Math.abs(y.im)) {
					if (abs_breal === 0) throw new PyError("division by zero", "ZeroDivisionError");
					const ratio = y.im / y.re, dd = y.re + y.im * ratio;
					return {
						t: "complex",
						re: (x.re + x.im * ratio) / dd,
						im: (x.im - x.re * ratio) / dd
					};
				}
				const ratio = y.re / y.im, dd = y.re * ratio + y.im;
				return {
					t: "complex",
					re: (x.re * ratio + x.im) / dd,
					im: (x.im * ratio - x.re) / dd
				};
			}
			case "pow": return complexPow(x, y);
			default: throw typeError("unsupported operand type");
		}
	}
	/** PyNumber_Negative. */
	function neg(a) {
		switch (a.t) {
			case "int": return {
				t: "int",
				v: -a.v
			};
			case "bool": return {
				t: "int",
				v: a.v ? -1n : 0n
			};
			case "float": return float(-a.v);
			case "complex": return {
				t: "complex",
				re: -a.re,
				im: -a.im
			};
			case "qty": return {
				t: "qty",
				q: {
					value: a.q.value * -1,
					dims: a.q.dims
				}
			};
			case "vector": return vector([
				-a.v[0],
				-a.v[1],
				-a.v[2]
			]);
			default: throw typeError(`bad operand type for unary -: '${typeName(a)}'`);
		}
	}
	/** PyNumber_Positive. */
	function pos(a) {
		switch (a.t) {
			case "int":
			case "float":
			case "complex": return a;
			case "bool": return {
				t: "int",
				v: a.v ? 1n : 0n
			};
			case "qty": return {
				t: "qty",
				q: {
					value: a.q.value,
					dims: a.q.dims
				}
			};
			case "vector": return vector([
				a.v[0],
				a.v[1],
				a.v[2]
			]);
			default: throw typeError(`bad operand type for unary +: '${typeName(a)}'`);
		}
	}
	/** repr(float): the shortest digits that read back, in Python's layout. `dot` keeps the ".0" of a whole number. */
	function floatRepr(x, dot = true) {
		if (Number.isNaN(x)) return "nan";
		if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
		if (x === 0) return (Object.is(x, -0) ? "-0" : "0") + (dot ? ".0" : "");
		const [m, e] = Math.abs(x).toExponential().split("e");
		const digits = m.replace(".", ""), exp = Number(e);
		let s;
		if (exp < -4 || exp >= 16) s = digits[0] + (digits.length > 1 ? "." + digits.slice(1) : "") + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
		else if (exp >= 0) s = digits.length <= exp + 1 ? digits.padEnd(exp + 1, "0") + (dot ? ".0" : "") : digits.slice(0, exp + 1) + "." + digits.slice(exp + 1);
		else s = "0." + "0".repeat(-exp - 1) + digits;
		return (x < 0 ? "-" : "") + s;
	}
	function complexRepr(re, im) {
		const r = floatRepr(re, false);
		const i = floatRepr(im, false);
		if (re === 0 && !Object.is(re, -0)) return `${i}j`;
		return `(${r}${im < 0 || Object.is(im, -0) || i.startsWith("-") ? "" : "+"}${i}j)`;
	}
	/** repr(str). */
	function strRepr(s) {
		const quote = s.includes("'") && !s.includes("\"") ? "\"" : "'";
		let out = quote;
		for (const ch of s) {
			const c = ch.codePointAt(0);
			if (ch === quote || ch === "\\") out += "\\" + ch;
			else if (ch === "\n") out += "\\n";
			else if (ch === "\r") out += "\\r";
			else if (ch === "	") out += "\\t";
			else if (c < 32 || c === 127) out += "\\x" + c.toString(16).padStart(2, "0");
			else if (c >= 128 && c < 160) out += "\\x" + c.toString(16).padStart(2, "0");
			else if (c === 173 || c >= 8232 && c <= 8233 || c >= 55296 && c <= 57343) out += "\\u" + c.toString(16).padStart(4, "0");
			else out += ch;
		}
		return out + quote;
	}
	/** repr(obj). */
	function repr(a) {
		switch (a.t) {
			case "int": return a.v.toString();
			case "float": return floatRepr(a.v);
			case "bool": return a.v ? "True" : "False";
			case "str": return strRepr(a.v);
			case "none": return "None";
			case "qty": return floatRepr(a.q.value) + (isDimless(a.q.dims) ? "" : " " + unitString(a.q.dims));
			case "complex": return complexRepr(a.re, a.im);
			case "list": return "[" + a.v.map(repr).join(", ") + "]";
			case "tuple": return a.v.length === 1 ? `(${repr(a.v[0])},)` : "(" + a.v.map(repr).join(", ") + ")";
			case "obj": return a.str;
			case "vector": return `Vector (${floatRepr(a.v[0])}, ${floatRepr(a.v[1])}, ${floatRepr(a.v[2])})`;
		}
	}
	/** str(obj). */
	var pyStr = (a) => a.t === "str" ? a.v : repr(a);
	function intToIndex(a, spec) {
		if (isIntLike(a)) return bigOf(a);
		throw typeError(`%${spec} format: an integer is required, not ${typeName(a)}`);
	}
	/** PyNumber_Long for a %d: ints, floats (truncated) and Quantity (its value, as a C long). */
	function longOf(a, spec) {
		if (isIntLike(a)) return bigOf(a);
		if (a.t === "float") {
			if (!Number.isFinite(a.v)) throw new PyError(Number.isNaN(a.v) ? "cannot convert float NaN to integer" : "cannot convert float infinity to integer", Number.isNaN(a.v) ? "ValueError" : "OverflowError");
			return BigInt(Math.trunc(a.v));
		}
		if (a.t === "qty") return BigInt(Math.trunc(a.q.value));
		throw typeError(`%${spec} format: a real number is required, not ${typeName(a)}`);
	}
	function floatArg(a, spec) {
		if (a.t === "float") return a.v;
		if (isIntLike(a)) return floatOfInt(bigOf(a));
		if (a.t === "qty") return a.q.value;
		throw typeError(`must be real number, not ${typeName(a)}`);
	}
	function expFormat(v, prec, upper) {
		const s = toNumber(v, "Scientific", prec);
		return upper ? s.toUpperCase() : s;
	}
	function genFormat(v, prec, alt, upper) {
		let s;
		if (!alt) s = toNumber(v, "Default", prec);
		else {
			const sci = toNumber(v, "Scientific", prec - 1);
			const X = Number(sci.slice(sci.indexOf("e") + 1));
			s = X >= -4 && X < prec ? toNumber(v, "Fixed", prec - 1 - X) : sci;
			if (!s.includes(".")) s = s.includes("e") ? s.replace("e", ".e") : s + ".";
		}
		return upper ? s.toUpperCase() : s;
	}
	/** PyUnicode_Format: the right operand is the one value, or the items of a tuple. */
	function percentFormat(fmt, arg) {
		const args = arg.t === "tuple" ? arg.v : [arg];
		let ai = 0;
		const next = () => {
			if (ai >= args.length) throw typeError("not enough arguments for format string");
			return args[ai++];
		};
		let out = "";
		const chars = Array.from(fmt);
		let i = 0;
		while (i < chars.length) {
			const ch = chars[i];
			if (ch !== "%") {
				out += ch;
				i++;
				continue;
			}
			i++;
			if (chars[i] === "(") {
				if (arg.t === "list") throw typeError("list indices must be integers or slices, not str");
				throw typeError("format requires a mapping");
			}
			const flags = {
				minus: false,
				plus: false,
				space: false,
				alt: false,
				zero: false
			};
			for (; i < chars.length; i++) {
				const f = chars[i];
				if (f === "-") flags.minus = true;
				else if (f === "+") flags.plus = true;
				else if (f === " ") flags.space = true;
				else if (f === "#") flags.alt = true;
				else if (f === "0") flags.zero = true;
				else break;
			}
			let width = -1, prec = -1;
			if (chars[i] === "*") {
				const w = next();
				if (!isIntLike(w)) throw typeError("* wants int");
				if (bigOf(w) > 9223372036854775807n || bigOf(w) < -9223372036854775808n) throw overflow("Python int too large to convert to C ssize_t");
				width = Number(bigOf(w));
				if (width < 0) {
					flags.minus = true;
					width = -width;
				}
				i++;
			} else {
				let w = "";
				while (i < chars.length && /[0-9]/.test(chars[i])) w += chars[i++];
				if (w) width = Number(w);
			}
			if (chars[i] === ".") {
				i++;
				if (chars[i] === "*") {
					const p = next();
					if (!isIntLike(p)) throw typeError("* wants int");
					if (bigOf(p) > 2147483647n || bigOf(p) < -2147483648n) throw overflow("Python int too large to convert to C int");
					prec = Math.max(0, Number(bigOf(p)));
					i++;
				} else {
					let p = "";
					while (i < chars.length && /[0-9]/.test(chars[i])) p += chars[i++];
					prec = p ? Number(p) : 0;
				}
			}
			if (i < chars.length && "hlL".includes(chars[i])) i++;
			if (i >= chars.length) throw new PyError("incomplete format", "ValueError");
			const conv = chars[i++];
			if (conv === "%" && !(flags.minus || flags.plus || flags.space || flags.alt || flags.zero || width >= 0 || prec >= 0)) {
				out += "%";
				continue;
			}
			const a = next();
			fits(width);
			fits(prec);
			let body, sign = "", numeric = true;
			switch (conv) {
				case "s":
					body = pyStr(a);
					numeric = false;
					if (prec >= 0) body = Array.from(body).slice(0, prec).join("");
					break;
				case "r":
					body = repr(a);
					numeric = false;
					if (prec >= 0) body = Array.from(body).slice(0, prec).join("");
					break;
				case "a":
					body = repr(a).replace(/[^\x00-\x7f]/gu, (c) => {
						const n = c.codePointAt(0);
						return n < 256 ? "\\x" + n.toString(16).padStart(2, "0") : n < 65536 ? "\\u" + n.toString(16).padStart(4, "0") : "\\U" + n.toString(16).padStart(8, "0");
					});
					numeric = false;
					if (prec >= 0) body = body.slice(0, prec);
					break;
				case "c":
					numeric = false;
					if (isIntLike(a)) {
						const n = bigOf(a);
						if (n < 0n || n > 1114111n) throw new PyError("%c arg not in range(0x110000)", "OverflowError");
						body = String.fromCodePoint(Number(n));
					} else if (a.t === "str" && Array.from(a.v).length === 1) body = a.v;
					else throw typeError("%c requires int or char");
					break;
				case "d":
				case "i":
				case "u": {
					const n = longOf(a, conv);
					sign = n < 0n ? "-" : flags.plus ? "+" : flags.space ? " " : "";
					body = (n < 0n ? -n : n).toString();
					if (prec >= 0) body = body.padStart(prec, "0");
					break;
				}
				case "x":
				case "X":
				case "o": {
					const n = intToIndex(a, conv);
					sign = n < 0n ? "-" : flags.plus ? "+" : flags.space ? " " : "";
					body = (n < 0n ? -n : n).toString(conv === "o" ? 8 : 16);
					if (conv === "X") body = body.toUpperCase();
					if (prec >= 0) body = body.padStart(prec, "0");
					if (flags.alt) body = (conv === "o" ? "0o" : conv === "x" ? "0x" : "0X") + body;
					break;
				}
				case "e":
				case "E":
				case "f":
				case "F":
				case "g":
				case "G": {
					const v = floatArg(a, conv);
					const p = prec < 0 ? 6 : prec;
					if (!Number.isFinite(v)) {
						body = Number.isNaN(v) ? "nan" : "inf";
						sign = v < 0 ? "-" : flags.plus ? "+" : flags.space ? " " : "";
						if ("EFG".includes(conv)) body = body.toUpperCase();
						flags.zero = false;
						break;
					}
					sign = v < 0 || Object.is(v, -0) ? "-" : flags.plus ? "+" : flags.space ? " " : "";
					const av = Math.abs(v);
					if (conv === "e" || conv === "E") {
						body = expFormat(av, p, conv === "E");
						if (flags.alt && p === 0) body = body.replace(/e/i, (m) => "." + m);
					} else if (conv === "f" || conv === "F") {
						body = toNumber(av, "Fixed", p);
						if (flags.alt && p === 0) body += ".";
					} else body = genFormat(av, p === 0 ? 1 : p, flags.alt, conv === "G");
					break;
				}
				default: {
					const c = conv.codePointAt(0);
					throw new PyError(`unsupported format character '${c >= 31 && c <= 126 ? conv : "?"}' (0x${c.toString(16)}) at index ${i - 1}`, "ValueError");
				}
			}
			let text = sign + body;
			if (width > text.length) {
				if (flags.minus) text = text.padEnd(width, " ");
				else if (flags.zero && numeric) text = sign + body.padStart(width - sign.length, "0");
				else text = text.padStart(width, " ");
			}
			out = sized(out.length + text.length, () => out + text);
		}
		if (ai < args.length && arg.t !== "list" && arg.t !== "vector") throw typeError("not all arguments converted during string formatting");
		return out;
	}
	function indexOf(i, what, len) {
		if (!isIntLike(i)) throw typeError(`${what} indices must be integers${what === "string" ? "" : " or slices"}, not '${typeName(i)}'`);
		let n = Number(bigOf(i));
		if (n < 0) n += len;
		if (n < 0 || n >= len) throw new PyError(`${what} index out of range`, "IndexError");
		return n;
	}
	/** PyObject_GetItem on a str, list or tuple; what Py::Sequence does to anything else. */
	function getItem(obj, index) {
		if (obj.t === "str") {
			const cps = Array.from(obj.v);
			return str(cps[indexOf(index, "string", cps.length)]);
		}
		if (obj.t === "list") return obj.v[indexOf(index, "list", obj.v.length)];
		if (obj.t === "tuple") return obj.v[indexOf(index, "tuple", obj.v.length)];
		throw typeError(`PyCXX: Error creating object of type N2Py7SeqBaseINS_6ObjectEEE from ${repr(obj)}`);
	}
	/** A slice object applied (PySlice_New + PyObject_GetItem). Each bound is None or an int. */
	function getSlice(obj, lo, hi, step) {
		const bound = (b) => {
			if (b === null || b.t === "none") return null;
			if (!isIntLike(b)) throw typeError("slice indices must be integers or None or have an __index__ method");
			return bigOf(b);
		};
		const items = obj.t === "str" ? Array.from(obj.v) : obj.t === "list" || obj.t === "tuple" ? obj.v : null;
		if (!items) throw typeError(`PyCXX: Error creating object of type N2Py7SeqBaseINS_6ObjectEEE from ${repr(obj)}`);
		const s = bound(step) ?? 1n;
		if (s === 0n) throw new PyError("slice step cannot be zero", "ValueError");
		const n = BigInt(items.length);
		const clamp = (b, dflt, lowest, highest) => {
			if (b === null) return dflt;
			if (b < 0n) {
				b += n;
				if (b < 0n) b = s < 0n ? lowest : 0n;
			} else if (b >= n) b = s < 0n ? highest : n;
			return b;
		};
		const start = clamp(bound(lo), s < 0n ? n - 1n : 0n, -1n, n - 1n);
		const stop = clamp(bound(hi), s < 0n ? -1n : n, -1n, n - 1n);
		const picked = [];
		if (s > 0n) for (let k = start; k < stop; k += s) picked.push(items[Number(k)]);
		else for (let k = start; k > stop; k += s) picked.push(items[Number(k)]);
		if (obj.t === "str") return str(picked.join(""));
		return obj.t === "list" ? {
			t: "list",
			v: picked
		} : {
			t: "tuple",
			v: picked
		};
	}
	/** Attribute access (ObjectIdentifier::Component::get on a Python value): what a number, a Quantity or a str offers here. */
	function getAttr(obj, name) {
		const noAttr = () => new PyError(`No attribute named '${name}'`, "AttributeError");
		switch (obj.t) {
			case "qty":
				if (name === "Value") return float(obj.q.value);
				if (name === "Unit") return {
					t: "obj",
					type: "Unit",
					str: unitObjectString(obj.q.dims)
				};
				if (name === "UserString") return str(userString(obj.q).text);
				throw noAttr();
			case "int":
			case "bool":
				if (name === "real" || name === "numerator") return {
					t: "int",
					v: bigOf(obj)
				};
				if (name === "imag") return int(0);
				if (name === "denominator") return int(1);
				throw noAttr();
			case "float":
				if (name === "real") return obj;
				if (name === "imag") return float(0);
				throw noAttr();
			case "complex":
				if (name === "real") return float(obj.re);
				if (name === "imag") return float(obj.im);
				throw noAttr();
			default: throw noAttr();
		}
	}
	/** Unit::representation(): "Unit: mm (1,0,0,0,0,0,0,0) [Length]". */
	function unitObjectString(dims) {
		const type = typeString(dims);
		return `Unit: ${unitString(dims)} (${dims.join(",")})${type ? ` [${type}]` : ""}`;
	}
	//#endregion
	//#region src/expr.ts
	var ZERO = ZERO$1;
	/** The error ParserExpression throws for a text it cannot read. */
	var parseError = (text) => new PyError(`Failed to parse expression '${text}'`, "ParserError", "syntax");
	var TERM = new Map(TERMINALS.map((t, i) => [t, i]));
	var T = (name) => TERM.get(name) ?? -1;
	var UNIT_TOKENS = Object.keys(UNITS).sort((a, b) => b.length - a.length);
	var escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	var RE_UNIT = new RegExp(UNIT_TOKENS.map(escapeRe).join("|"), "y");
	var RE_WS = /[ \t]+/y;
	var RE_NL = /\n/y;
	var RE_STRING = /<<(?:\\[\s\S]|[^\\>\n])*>>/y;
	var RE_CHAR = /[%+()=/*^,.{}[\]:;@?#]/y;
	var RE_N1 = /[0-9]*\.[0-9]+(?:[eE][-+]?[0-9]+)?/y;
	var RE_N2 = /[0-9]*,[0-9]+(?:[eE][-+]?[0-9]+)?/y;
	var RE_N3 = /[0-9]+[eE][-+]?[0-9]+/y;
	var RE_N4 = /[0-9]+/y;
	var RE_CONST = /None|True|true|False|false|pi|e/y;
	var RE_CELL1 = /\$[A-Za-z]+\$[0-9]+/y;
	var RE_CELL2 = /[A-Za-z]{1,2}\$[0-9]+/y;
	var RE_CELL3 = /\$[A-Za-z]{1,2}[0-9]+/y;
	var RE_FUNC = /\p{L}\p{M}*(?:\p{L}\p{M}*|\p{N}|_)*[\x10\t]*\(/uy;
	var RE_IDENT = /(?:\p{L}\p{M}*|_)(?:\p{L}\p{M}*|\p{N}|_|@)*/uy;
	var SIMPLE_OPS = [
		"==",
		"!=",
		">=",
		"<=",
		">",
		"<"
	];
	/** The function names Expression.y's lexer registers (initParser). */
	var FUNCTIONS = /* @__PURE__ */ new Set([
		"abs",
		"acos",
		"asin",
		"atan",
		"atan2",
		"cath",
		"cbrt",
		"ceil",
		"cos",
		"cosh",
		"exp",
		"floor",
		"hypot",
		"log",
		"log10",
		"mod",
		"pow",
		"round",
		"sin",
		"sinh",
		"sqrt",
		"tan",
		"tanh",
		"trunc",
		"vangle",
		"vcross",
		"vdot",
		"vlinedist",
		"vlinesegdist",
		"vlineproj",
		"vnormalize",
		"vplanedist",
		"vplaneproj",
		"vscale",
		"vscalex",
		"vscaley",
		"vscalez",
		"minvert",
		"mrotate",
		"mrotatex",
		"mrotatey",
		"mrotatez",
		"mscale",
		"mtranslate",
		"create",
		"list",
		"matrix",
		"placement",
		"rotation",
		"rotationx",
		"rotationy",
		"rotationz",
		"str",
		"parsequant",
		"translationm",
		"tuple",
		"vector",
		"address",
		"hiddenref",
		"href",
		"not",
		"average",
		"count",
		"max",
		"min",
		"stddev",
		"sum",
		"and",
		"or"
	]);
	var CONSTANTS = {
		pi: {
			name: "pi",
			v: Math.PI
		},
		e: {
			name: "e",
			v: Math.E
		},
		None: {
			name: "None",
			v: 0
		},
		True: {
			name: "True",
			v: 1
		},
		true: {
			name: "True",
			v: 1
		},
		False: {
			name: "False",
			v: 0
		},
		false: {
			name: "False",
			v: 0
		}
	};
	/** num_change (Expression.l): the digits of a number with `grp` left out and `dez` as the point; a text of 40 characters or more is 0. */
	function numChange(text, dez, grp) {
		let t = "", n = 0;
		for (const c of text) {
			if (c === grp) continue;
			t += c === dez && dez !== "." ? "." : c;
			if (++n > 39) return 0;
		}
		const v = Number(t);
		if (v === 0 && /[1-9]/.test(t.split(/[eE]/)[0])) throw new PyError("Number underflow.", "ArithmeticError");
		if (v === Infinity || v === -Infinity) throw new PyError("Number overflow.", "OverflowError");
		return v;
	}
	/** unquote (Expression.cpp): the text of a <<string>>, escapes resolved. It works on bytes: an escape it does not know drops
	*  one byte, so a backslash before a character of more than one byte leaves the rest of that character behind, and the text
	*  is then not UTF-8 (`bad` says what Python says about it when the string is made). */
	function unquote(lexeme) {
		const bytes = new TextEncoder().encode(lexeme);
		const out = [];
		let escaped = false;
		for (let i = 2; i < bytes.length - 2; i++) {
			const c = bytes[i];
			if (escaped) {
				if (c === 116) out.push(9);
				else if (c === 110) out.push(10);
				else if (c === 114) out.push(13);
				else if (c === 92 || c === 39 || c === 34) out.push(c);
				escaped = false;
			} else if (c === 92) escaped = true;
			else out.push(c);
		}
		try {
			return {
				s: new TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array(out)),
				bad: null
			};
		} catch {
			let at = 0;
			while (at < out.length) {
				const c = out[at];
				const len = c < 128 ? 1 : c >= 194 && c < 224 ? 2 : c >= 224 && c < 240 ? 3 : c >= 240 && c < 245 ? 4 : 0;
				if (len === 0) break;
				if (at + len > out.length) return {
					s: "",
					bad: `'utf-8' codec can't decode byte 0x${c.toString(16)} in position ${at}: unexpected end of data`
				};
				if (out.slice(at + 1, at + len).some((x) => (x & 192) !== 128)) return {
					s: "",
					bad: `'utf-8' codec can't decode byte 0x${c.toString(16)} in position ${at}: invalid continuation byte`
				};
				at += len;
			}
			return {
				s: "",
				bad: `'utf-8' codec can't decode byte 0x${(out[at] ?? 0).toString(16)} in position ${at}: invalid start byte`
			};
		}
	}
	var Lexer = class {
		text;
		names;
		i = 0;
		constructor(text, names) {
			this.text = text;
			this.names = names;
		}
		at(re) {
			re.lastIndex = this.i;
			const m = re.exec(this.text);
			return m ? m[0] : null;
		}
		/** The next token, longest match first and the earlier rule on a tie; a character no rule takes is skipped (flex's default rule). */
		next() {
			for (;;) {
				if (this.i >= this.text.length) return { n: 0 };
				let len = 0, kind = "";
				const consider = (k, m) => {
					if (m !== null && m.length > len) {
						len = m.length;
						kind = k;
					}
				};
				consider("ws", this.at(RE_WS));
				consider("nl", this.at(RE_NL));
				consider("str", this.at(RE_STRING));
				consider("char", this.at(RE_CHAR));
				for (const op of SIMPLE_OPS) if (this.text.startsWith(op, this.i)) consider("op", op);
				if (this.text[this.i] === "-") consider("minus", "-");
				if (this.text[this.i] === "−") consider("minus", "−");
				consider("unit", this.at(RE_UNIT));
				consider("n1", this.at(RE_N1));
				consider("n2", this.at(RE_N2));
				consider("n3", this.at(RE_N3));
				consider("n4", this.at(RE_N4));
				consider("const", this.at(RE_CONST));
				consider("cell", this.at(RE_CELL1));
				consider("cell", this.at(RE_CELL2));
				consider("cell", this.at(RE_CELL3));
				consider("func", this.at(RE_FUNC));
				consider("id", this.at(RE_IDENT));
				if (len === 0) {
					this.i += String.fromCodePoint(this.text.codePointAt(this.i)).length;
					continue;
				}
				const lexeme = this.text.slice(this.i, this.i + len);
				this.i += len;
				switch (kind) {
					case "ws":
					case "nl": continue;
					case "str": return {
						n: T("STRING"),
						v: unquote(lexeme)
					};
					case "char": return {
						n: T(`'${lexeme}'`),
						v: lexeme
					};
					case "op": return { n: T({
						"==": "EQ",
						"!=": "NEQ",
						">": "GT",
						"<": "LT",
						">=": "GTE",
						"<=": "LTE"
					}[lexeme]) };
					case "minus": return { n: T("MINUSSIGN") };
					case "unit": {
						if (this.names.has(lexeme)) return {
							n: T("IDENTIFIER"),
							v: lexeme
						};
						const [value, dims] = UNITS[lexeme];
						return {
							n: T(lexeme === "\"" || lexeme === "'" ? "USUNIT" : "UNIT"),
							v: {
								q: {
									value,
									dims
								},
								s: lexeme
							}
						};
					}
					case "n1":
					case "n2":
					case "n3": {
						const v = kind === "n2" ? numChange(lexeme, ",", ".") : numChange(lexeme, kind === "n1" ? "." : ",", kind === "n1" ? "," : ".");
						return {
							n: T(v === 1 ? "ONE" : "NUM"),
							v
						};
					}
					case "n4": {
						const v = BigInt(lexeme);
						if (v >= 9223372036854775807n) throw new PyError("Integer overflow", "OverflowError");
						return v === 1n ? {
							n: T("ONE"),
							v: 1
						} : {
							n: T("INTEGER"),
							v: Number(v)
						};
					}
					case "const":
						if (this.names.has(lexeme)) return {
							n: T("IDENTIFIER"),
							v: lexeme
						};
						return {
							n: T("CONSTANT"),
							v: CONSTANTS[lexeme]
						};
					case "cell": return {
						n: T("CELLADDRESS"),
						v: lexeme
					};
					case "func": {
						const name = lexeme.slice(0, -1).replace(/[ \t\n\v\f\r]+$/, "");
						return {
							n: T("FUNC"),
							v: {
								name,
								known: FUNCTIONS.has(name)
							}
						};
					}
					default: return {
						n: T("IDENTIFIER"),
						v: lexeme
					};
				}
			}
		}
	};
	/** What each function wants of its argument count, in the words FunctionExpression's constructor uses (null: any count, but one). */
	var ARITY = (() => {
		const one = [(n) => n === 1, "exactly one required."];
		const two = [(n) => n === 2, "exactly two required."];
		const twoThree = [(n) => n >= 2 && n <= 3, "exactly two, or three required."];
		const three = [(n) => n === 3, "exactly three required."];
		const atLeastOne = [(n) => n >= 1, "at least one required."];
		const out = {};
		for (const f of [
			"abs",
			"acos",
			"asin",
			"atan",
			"cbrt",
			"ceil",
			"cos",
			"cosh",
			"exp",
			"floor",
			"hiddenref",
			"href",
			"log",
			"log10",
			"minvert",
			"rotationx",
			"rotationy",
			"rotationz",
			"round",
			"sin",
			"sinh",
			"sqrt",
			"str",
			"parsequant",
			"tan",
			"tanh",
			"trunc",
			"vnormalize",
			"not"
		]) out[f] = one;
		out.placement = [(n) => n <= 3, "exactly one, two, or three required."];
		out.translationm = [(n) => n === 1 || n === 3, "exactly one or three required."];
		for (const f of [
			"atan2",
			"mod",
			"mrotatex",
			"mrotatey",
			"mrotatez",
			"pow",
			"vangle",
			"vcross",
			"vdot",
			"vscalex",
			"vscaley",
			"vscalez"
		]) out[f] = two;
		for (const f of [
			"address",
			"cath",
			"hypot",
			"rotation"
		]) out[f] = twoThree;
		for (const f of ["mtranslate", "mscale"]) out[f] = [(n) => n === 2 || n === 4, "exactly two or four required."];
		out.mrotate = [(n) => n >= 2 && n <= 4, "exactly two, three, or four required."];
		for (const f of [
			"vector",
			"vlinedist",
			"vlinesegdist",
			"vlineproj",
			"vplanedist",
			"vplaneproj"
		]) out[f] = three;
		out.vscale = [(n) => n === 4, "exactly four required."];
		out.matrix = [(n) => n <= 16, "exactly 16 or less required."];
		for (const f of [
			"average",
			"count",
			"create",
			"max",
			"min",
			"stddev",
			"sum",
			"and",
			"or"
		]) out[f] = atLeastOne;
		out.list = null;
		out.tuple = null;
		return out;
	})();
	/** Expression::priority(): the operators' (OperatorExpression::priority), a conditional's, and 20 for the rest. */
	function priority(n) {
		switch (n.k) {
			case "op": switch (n.op) {
				case "==":
				case "!=":
				case "<":
				case ">":
				case "<=":
				case ">=": return 1;
				case "+":
				case "-": return 3;
				case "*":
				case "/":
				case "%": return 4;
				case "^": return 5;
				default: return 6;
			}
			case "neg":
			case "pos": return 6;
			case "cond": return 2;
			default: return 20;
		}
	}
	var isRightAssociative = (op) => op === "+" || op === "*";
	var isCommutative = (op) => op === "==" || op === "!=" || op === "+" || op === "*";
	/** The text of a number as Expression.cpp prints it: setprecision(15), the default float format. */
	var numberText = (v) => toNumber(v, "Default", 15);
	/** App::quote: <<text>> with the characters the lexer reads as escapes written as escapes. */
	function quote(s) {
		let out = "<<";
		for (const c of s) if (c === "\n") out += "\\n";
		else if (c === "	") out += "\\t";
		else if (c === "\r") out += "\\r";
		else if (c === "\\") out += "\\\\";
		else if (c === "\"") out += "\\\"";
		else if (c === "'") out += "\\'";
		else out += c;
		return out + ">>";
	}
	/** ObjectIdentifier::toString: the property, a '.' before it if it is the owner's own and attributes follow. */
	function pathText(p) {
		const props = p.names.map((n, i) => i === 0 ? n : "." + n).join("");
		const subs = p.sub.map((c) => idCompText(c)).join("");
		if (p.plain) return props + subs;
		if (p.forced && p.obj) return (p.doc ? refText(p.doc) + "#" : "") + refText(p.obj) + "." + props + subs;
		return (p.local || p.names.length > 1 ? "." : "") + props + subs;
	}
	function idCompText(c) {
		switch (c.k) {
			case "attr": return "." + c.name;
			case "array": return `[${c.i}]`;
			case "map": return `[${quote(c.key)}]`;
			case "range": return `[${c.b}:${c.e === null ? "" : c.e}${c.s !== 1 ? ":" + c.s : ""}]`;
		}
	}
	/** Expression::toString. */
	function toText(n) {
		switch (n.k) {
			case "num": return numberText(n.v);
			case "const": return n.name;
			case "unit": return n.s;
			case "str": return quote(n.s);
			case "range": return `${n.a}:${n.b}`;
			case "var": {
				let s = pathText(n.path);
				for (const c of n.comps) if ("name" in c) s += "." + c.name;
				else s += `[${c.e1 ? toText(c.e1) : ""}${c.e2 || c.range ? ":" : ""}${c.e2 ? toText(c.e2) : ""}${c.e3 ? ":" + toText(c.e3) : ""}]`;
				return s;
			}
			case "neg":
			case "pos": {
				const parens = priority(n.a) < 6;
				return (n.k === "neg" ? "-" : "+") + (parens ? "(" : "") + toText(n.a) + (parens ? ")" : "");
			}
			case "op": {
				let left = false;
				n.l.k === "op" && n.l.op;
				if (priority(n.l) < priority(n)) left = true;
				if (n.op === "unit" && n.l.k !== "num" && n.l.k !== "const") left = true;
				let s = left ? `(${toText(n.l)})` : toText(n.l);
				s += n.op === "unit" ? " " : ` ${n.op} `;
				let right = false;
				const rop = n.r.k === "op" ? n.r.op : null;
				if (priority(n.r) < priority(n)) right = true;
				else if (rop === n.op) {
					if (!isRightAssociative(n.op)) right = true;
					else if (!isCommutative(n.op)) right = true;
				} else if (priority(n.r) === priority(n)) {
					if (!isRightAssociative(n.op) || rop === "%") right = true;
				}
				s += right ? `(${toText(n.r)})` : toText(n.r);
				return s;
			}
			case "fn": return `${n.name}(${n.args.map(toText).join("; ")})`;
			case "cond": {
				const wrap = (x) => priority(x) <= 2 ? `(${toText(x)})` : toText(x);
				return `${toText(n.c)} ? ${wrap(n.t)} : ${wrap(n.f)}`;
			}
		}
	}
	/** The suffix FreeCAD appends to an error: "\nin expression: ...". */
	var inExpr = (msg, n) => `${msg}\nin expression: ${toText(n)}`;
	var essentiallyEqual = (a, b) => Math.abs(a - b) <= Math.min(Math.abs(a), Math.abs(b)) * Number.EPSILON;
	var numLike = (n) => !!n && (n.k === "num" || n.k === "const");
	var essentiallyInteger = (v) => Number.isFinite(v) && Number.isInteger(v) && Math.abs(v) <= 0x8000000000000000 ? v : null;
	/** VariableExpression::addComponent: a constant index or range is folded into the identifier, the rest stays an expression. */
	function addComponent(n, c) {
		if (n.comps.length === 0) {
			if ("name" in c) {
				n.path.sub.push({
					k: "attr",
					name: c.name
				});
				return;
			}
			folding: do {
				if (!c.e1 && !c.e2) {
					n.path.sub.push({
						k: "range",
						b: 0,
						e: null,
						s: 1
					});
					return;
				}
				let l1 = 0, l2 = 0;
				if (c.e3) {
					if (!numLike(c.e3) || !essentiallyEqual(c.e3.v, 1)) break folding;
				}
				if (c.e1) {
					if (!numLike(c.e1)) {
						if (c.e2 || c.e3) break folding;
						if (c.e1.k !== "str") break folding;
						n.path.sub.push({
							k: "map",
							key: c.e1.s
						});
						return;
					}
					const i1 = essentiallyInteger(c.e1.v);
					if (i1 === null) break folding;
					l1 = i1;
					if (!c.range) {
						n.path.sub.push({
							k: "array",
							i: l1
						});
						return;
					}
					if (!c.e2) {
						n.path.sub.push({
							k: "range",
							b: l1,
							e: l2,
							s: 1
						});
						return;
					}
				}
				if (numLike(c.e2)) {
					const i2 = essentiallyInteger(c.e2.v);
					if (i2 !== null) {
						n.path.sub.push({
							k: "range",
							b: l1,
							e: i2,
							s: 1
						});
						return;
					}
				}
			} while (false);
		}
		n.comps.push(c);
	}
	var op = (o, l, r) => ({
		k: "op",
		op: o,
		l,
		r
	});
	var emptyPath = () => ({
		doc: null,
		obj: null,
		local: false,
		names: [],
		sub: []
	});
	var mkVar = (path) => ({
		k: "var",
		path,
		comps: []
	});
	/** FunctionExpression's constructor: the checks on the name and the number of arguments. */
	function makeFunction(tok, args) {
		if (!tok.known) throw new PyError("Unknown function", "ParserError", "syntax");
		const node = {
			k: "fn",
			f: tok.name,
			name: tok.name,
			args
		};
		const rule = ARITY[tok.name];
		if (rule && !rule[0](args.length)) throw new PyError(inExpr(`Invalid number of arguments: ${rule[1]}`, node), "ExpressionError");
		return node;
	}
	/** The semantic actions, by the text of the rule they belong to (expr-grammar.ts has it with each rule). */
	var ACTIONS = {
		"input: exp": (v, c) => {
			c.result = v[0];
			c.value = true;
		},
		"input: unit_exp": (v, c) => {
			c.result = v[0];
			c.unit = true;
		},
		"unit_num: num unit_exp %prec NUM_AND_UNIT": (v) => op("unit", v[0], v[1]),
		"unit_num: '(' exp ')' unit_exp %prec NUM_AND_UNIT": (v) => op("unit", v[1], v[3]),
		"unit_num: num us_building_unit num us_building_unit %prec NUM_AND_UNIT": (v) => op("+", op("unit", v[0], v[1]), op("unit", v[2], v[3])),
		"exp: num": (v) => v[0],
		"exp: unit_num": (v) => v[0],
		"exp: STRING": (v) => ({
			k: "str",
			s: v[0].s,
			...v[0].bad ? { bad: v[0].bad } : {}
		}),
		"exp: identifier": (v) => mkVar(v[0]),
		"exp: MINUSSIGN exp %prec NEG": (v) => ({
			k: "neg",
			a: v[1]
		}),
		"exp: '+' exp %prec POS": (v) => ({
			k: "pos",
			a: v[1]
		}),
		"exp: exp '+' exp": (v) => op("+", v[0], v[2]),
		"exp: exp MINUSSIGN exp": (v) => op("-", v[0], v[2]),
		"exp: exp '*' exp": (v) => op("*", v[0], v[2]),
		"exp: exp '/' exp": (v) => op("/", v[0], v[2]),
		"exp: exp '%' exp": (v) => op("%", v[0], v[2]),
		"exp: exp '/' unit_exp": (v) => op("/", v[0], v[2]),
		"exp: exp '^' exp": (v) => op("^", v[0], v[2]),
		"exp: exp EQ exp": (v) => op("==", v[0], v[2]),
		"exp: exp NEQ exp": (v) => op("!=", v[0], v[2]),
		"exp: exp LT exp": (v) => op("<", v[0], v[2]),
		"exp: exp GT exp": (v) => op(">", v[0], v[2]),
		"exp: exp GTE exp": (v) => op(">=", v[0], v[2]),
		"exp: exp LTE exp": (v) => op("<=", v[0], v[2]),
		"exp: indexable": (v) => v[0],
		"exp: FUNC args ')'": (v) => makeFunction(v[0], v[1]),
		"exp: exp '?' exp ':' exp": (v) => ({
			k: "cond",
			c: v[0],
			t: v[2],
			f: v[4]
		}),
		"exp: '(' exp ')'": (v) => v[1],
		"num: ONE": (v) => ({
			k: "num",
			v: v[0]
		}),
		"num: NUM": (v) => ({
			k: "num",
			v: v[0]
		}),
		"num: INTEGER": (v) => ({
			k: "num",
			v: v[0]
		}),
		"num: CONSTANT": (v) => ({
			k: "const",
			name: v[0].name,
			v: v[0].v
		}),
		"args: exp": (v) => [v[0]],
		"args: range": (v) => [v[0]],
		"args: args ',' exp": (v) => [...v[0], v[2]],
		"args: args ';' exp": (v) => [...v[0], v[2]],
		"args: args ',' range": (v) => [...v[0], v[2]],
		"args: args ';' range": (v) => [...v[0], v[2]],
		"range: id_or_cell ':' id_or_cell": (v) => ({
			k: "range",
			a: v[0],
			b: v[2]
		}),
		"us_building_unit: USUNIT": (v) => ({
			k: "unit",
			q: v[0].q,
			s: v[0].s
		}),
		"other_unit: UNIT": (v) => ({
			k: "unit",
			q: v[0].q,
			s: v[0].s
		}),
		"unit_exp: other_unit": (v) => v[0],
		"unit_exp: us_building_unit": (v) => v[0],
		"unit_exp: unit_exp '/' unit_exp": (v) => op("/", v[0], v[2]),
		"unit_exp: unit_exp '*' unit_exp": (v) => op("*", v[0], v[2]),
		"unit_exp: unit_exp '^' integer": (v) => op("^", v[0], {
			k: "num",
			v: v[2]
		}),
		"unit_exp: unit_exp '^' MINUSSIGN integer": (v) => op("^", v[0], {
			k: "neg",
			a: {
				k: "num",
				v: v[3]
			}
		}),
		"unit_exp: '(' unit_exp ')'": (v) => v[1],
		"integer: INTEGER": (v) => v[0],
		"integer: ONE": (v) => v[0],
		"id_or_cell: IDENTIFIER": (v) => v[0],
		"id_or_cell: CELLADDRESS": (v) => v[0],
		"identifier: id_or_cell": (v) => ({
			...emptyPath(),
			names: [v[0]]
		}),
		"identifier: iden": (v) => v[0],
		"iden: '.' STRING '.' id_or_cell": (v) => ({
			...emptyPath(),
			local: true,
			names: [v[3]]
		}),
		"iden: '.' id_or_cell": (v) => ({
			...emptyPath(),
			local: true,
			names: [v[1]]
		}),
		"iden: object '.' STRING '.' id_or_cell": (v) => ({
			...emptyPath(),
			obj: v[0],
			names: [v[4]]
		}),
		"iden: object '.' id_or_cell": (v, c) => c.resolveAmbiguity ? c.resolveAmbiguity(v[0], v[2], c.owner) : {
			...emptyPath(),
			names: v[0].name === c.owner ? [v[2]] : [v[0].name, v[2]]
		},
		"iden: document '#' object '.' id_or_cell": (v) => ({
			...emptyPath(),
			doc: v[0],
			obj: v[2],
			names: [v[4]]
		}),
		"iden: document '#' object '.' STRING '.' id_or_cell": (v) => ({
			...emptyPath(),
			doc: v[0],
			obj: v[2],
			names: [v[6]]
		}),
		"iden: iden '.' IDENTIFIER": (v) => ({
			...v[0],
			names: [...v[0].names, v[2]]
		}),
		"indexer: '[' exp ']'": (v) => ({
			e1: v[1],
			e2: null,
			e3: null,
			range: false
		}),
		"indexer: '[' exp ':' ']'": (v) => ({
			e1: v[1],
			e2: null,
			e3: null,
			range: true
		}),
		"indexer: '[' ':' exp ']'": (v) => ({
			e1: null,
			e2: v[2],
			e3: null,
			range: true
		}),
		"indexer: '[' ':' ':' exp ']'": (v) => ({
			e1: null,
			e2: null,
			e3: v[3],
			range: true
		}),
		"indexer: '[' exp ':' exp ']'": (v) => ({
			e1: v[1],
			e2: v[3],
			e3: null,
			range: true
		}),
		"indexer: '[' exp ':' ':' exp ']'": (v) => ({
			e1: v[1],
			e2: null,
			e3: v[4],
			range: true
		}),
		"indexer: '[' ':' exp ':' exp ']'": (v) => ({
			e1: null,
			e2: v[2],
			e3: v[4],
			range: true
		}),
		"indexer: '[' exp ':' exp ':' exp ']'": (v) => ({
			e1: v[1],
			e2: v[3],
			e3: v[5],
			range: true
		}),
		"indexable: identifier indexer": (v) => {
			const n = mkVar(v[0]);
			addComponent(n, v[1]);
			return n;
		},
		"indexable: indexable indexer": (v) => {
			addComponent(v[0], v[1]);
			return v[0];
		},
		"indexable: indexable '.' IDENTIFIER": (v) => {
			addComponent(v[0], { name: v[2] });
			return v[0];
		},
		"document: STRING": (v) => ({
			name: v[0].s,
			str: true
		}),
		"document: IDENTIFIER": (v) => ({
			name: v[0],
			str: false
		}),
		"object: STRING": (v) => ({
			name: v[0].s,
			str: true
		}),
		"object: id_or_cell": (v) => ({
			name: v[0],
			str: false
		})
	};
	var RULE_ACTIONS = RULES.map(([, , text]) => {
		const a = ACTIONS[text];
		if (!a && text !== "$accept: input $end") throw new Error(`expr.ts has no action for the grammar rule "${text}": regenerate expr-grammar.ts and update ACTIONS`);
		return a;
	});
	/** Parse an expression (without a leading "="), as Expression.y does, building FreeCAD's expression classes. `names` are
	*  the parameters it may use: a unit's or constant's name among them reads as the parameter. Throws what FreeCAD throws:
	*  ParserError for text that is not an expression ("Failed to parse expression '...'"), and the lexer's and
	*  constructors' own errors. `owner` is the name of the object the expression belongs to. */
	function parseExpr(text, names = /* @__PURE__ */ new Set(), owner, resolveAmbiguity) {
		const ctx = runParser(text, names, owner, resolveAmbiguity);
		if (!ctx.result) throw new PyError(`Unknown error in expression '${text}'`, "ParserError", "syntax");
		if (!ctx.value) throw new PyError("Expression can not evaluate to a value.", "FreeCADError", "syntax");
		return ctx.result;
	}
	function runParser(text, names, owner, resolveAmbiguity) {
		const lexer = new Lexer(text, names);
		const ctx = {
			result: null,
			value: false,
			unit: false,
			owner,
			resolveAmbiguity
		};
		const states = [0];
		const values = [void 0];
		let tok = null;
		for (;;) {
			const [shifts, reds, def, gotos, needsToken] = STATES[states[states.length - 1]];
			let action = null;
			if (needsToken) {
				tok ??= lexer.next();
				for (let i = 0; i < shifts.length; i += 2) if (shifts[i] === tok.n) {
					action = { shift: shifts[i + 1] };
					break;
				}
				if (!action) {
					for (let i = 0; i < reds.length; i += 2) if (reds[i] === tok.n) {
						action = { reduce: reds[i + 1] };
						break;
					}
				}
			}
			if (!action) {
				if (def < 0) throw parseError(text);
				action = { reduce: def };
			}
			if ("shift" in action) {
				if (action.shift < 0) break;
				states.push(action.shift);
				values.push(tok.v);
				tok = null;
				continue;
			}
			const [lhs, len] = RULES[action.reduce];
			const args = values.splice(values.length - len, len);
			states.length -= len;
			const out = RULE_ACTIONS[action.reduce](args, ctx);
			values.push(out);
			const g = STATES[states[states.length - 1]][3];
			let next = -1;
			for (let i = 0; i < g.length; i += 2) if (g[i] === lhs) {
				next = g[i + 1];
				break;
			}
			if (next < 0) throw parseError(text);
			states.push(next);
		}
		return ctx;
	}
	/** ExpressionParser::parseUnit: a unit expression (or 1/unit), simplified: its dimensions and scaler ("cm": Length, 10). */
	function parseUnit(text) {
		let ctx;
		try {
			ctx = runParser(text, /* @__PURE__ */ new Set());
		} catch (e) {
			if (e instanceof PyError && e.kind === "syntax" && e.message === `Failed to parse expression '${text}'`) throw new PyError("Failed to parse expression.", "ParserError", "syntax");
			throw e;
		}
		const r = ctx.result;
		if (!r) throw new PyError("Unknown error in expression", "ParserError", "syntax");
		if (!(ctx.unit || r.k === "op" && r.op === "/" && numLike(r.l) && r.r.k === "unit" && essentiallyEqual(r.l.v, 1))) throw new PyError("Expression is not a unit.", "ExpressionError");
		const q = asQuantity(ev(r, { vars: {} }));
		return {
			dims: q.dims,
			scaler: q.value
		};
	}
	var firstTokens = (s) => {
		const lx = new Lexer(s, /* @__PURE__ */ new Set());
		return [lx.next().n, lx.next().n];
	};
	/** ExpressionParser::isTokenAUnit: the text is one UNIT token (a US building unit, " or ', is not). */
	function isTokenAUnit(s) {
		const [a, b] = firstTokens(s);
		return b === 0 && a === T("UNIT");
	}
	/** ExpressionParser::isTokenAConstant. */
	function isTokenAConstant(s) {
		const [a, b] = firstTokens(s);
		return b === 0 && a === T("CONSTANT");
	}
	var isPyVal = (x) => "t" in x;
	function propertyValue(x) {
		if (isPyVal(x)) return x;
		return isDimless(x.dims) ? float(x.value) : {
			t: "qty",
			q: x
		};
	}
	var rt = (message) => new PyError(message, "RuntimeError");
	var refText = (r) => r.str ? `<<${r.name}>>` : r.name;
	function resolveProperty(n, env) {
		const owner = env.owner ?? "", doc = env.doc ?? "";
		const p = n.path;
		if (env.resolve && (p.doc && p.doc.name !== doc || p.obj && p.obj.name !== owner || p.names.length >= 2 && !Object.prototype.hasOwnProperty.call(env.vars, p.names[0]))) {
			const r = env.resolve(p);
			if (r) return {
				value: propertyValue(r.value),
				rest: r.rest
			};
		}
		if (p.doc && p.doc.name !== doc) throw rt(`Document '${refText(p.doc)}' not found in '${p.doc.name}'`);
		if (p.obj && p.obj.name !== owner) throw rt(`Document object '${refText(p.obj)}' not found in '${doc}'`);
		const prop = p.names[0];
		if (!Object.prototype.hasOwnProperty.call(env.vars, prop)) throw rt(`Property '${prop}' not found in '${owner}'`);
		return {
			value: propertyValue(env.vars[prop]),
			rest: p.names.slice(1)
		};
	}
	/** ObjectIdentifier::Component::get: an attribute, index, key or slice the parser folded into the name. */
	function applyIdComp(c, v) {
		switch (c.k) {
			case "attr": return getAttr(v, c.name);
			case "array": return getItem(v, int(c.i));
			case "map": return mapItem(v, c.key);
			case "range": return getSlice(v, int(c.b), c.e === null ? null : int(c.e), c.s === 1 ? null : int(c.s));
		}
	}
	/** Py::Mapping(obj).getItem(key) with a string key. */
	function mapItem(v, key) {
		if (v.t === "str") throw new PyError("string indices must be integers, not 'str'", "TypeError");
		if (v.t === "list" || v.t === "tuple") throw new PyError(`${v.t} indices must be integers or slices, not str`, "TypeError");
		throw new PyError(`PyCXX: Error creating object of type N2Py7MapBaseINS_6ObjectEEE from ${repr(v)}`, "TypeError");
	}
	function evalVar(n, env) {
		const { value, rest } = resolveProperty(n, env);
		let v = value;
		for (const name of rest) v = getAttr(v, name);
		for (const c of n.path.sub) v = applyIdComp(c, v);
		for (const c of n.comps) v = applyExprComp(n, c, v, env);
		return v;
	}
	/** Expression::Component::get: an index or a slice by expressions, with the owner's text on an error. */
	function applyExprComp(owner, c, v, env) {
		if ("name" in c) return getAttr(v, c.name);
		const wrap = (f) => {
			try {
				return f();
			} catch (e) {
				if (e instanceof PyError && !e.message.includes("\nin expression: ")) throw new PyError(inExpr(e.message, owner), e.etype, e.kind);
				throw e;
			}
		};
		if (!c.range && !c.e2 && !c.e3) {
			const index = ev(c.e1, env);
			return wrap(() => {
				if (v.t === "str" || v.t === "list" || v.t === "tuple") return getItem(v, index);
				if (index.t !== "int" && index.t !== "bool") throw new PyError(`'${typeName(index)}' object cannot be interpreted as an integer`, "TypeError");
				return getItem(v, index);
			});
		}
		const a = c.e1 ? ev(c.e1, env) : null, b = c.e2 ? ev(c.e2, env) : null, s = c.e3 ? ev(c.e3, env) : null;
		return wrap(() => {
			if (v.t !== "str" && v.t !== "list" && v.t !== "tuple") throw new PyError(`'${typeName(v)}' object is not subscriptable`, "TypeError");
			return getSlice(v, a, b, s);
		});
	}
	function withExpr(n, f) {
		try {
			return f();
		} catch (e) {
			if (e instanceof PyError && !e.raw && !e.message.includes("\nin expression: ")) throw new PyError(inExpr(e.message, n), e.etype, e.kind);
			throw e;
		}
	}
	var OPERATOR_TO_BIN = {
		"+": "add",
		"-": "sub",
		"*": "mul",
		"/": "div",
		"%": "mod",
		"^": "pow",
		unit: "mul"
	};
	var OPERATOR_TO_CMP = {
		"==": "eq",
		"!=": "ne",
		"<": "lt",
		"<=": "le",
		">": "gt",
		">=": "ge"
	};
	var supportedOperand = (a) => isNumeric(a) || a.t === "str" || a.t === "list" || a.t === "obj";
	/** OperatorExpression's calc(): for security only numbers, strings and lists are accepted, and then Python's operators run. */
	function calc(n, o, left, right, env) {
		const l = ev(left, env);
		if (!supportedOperand(l)) throw new PyError(inExpr("Unsupported operator", n), "TypeError");
		if (o === "pos") return withExpr(n, () => pos(l));
		if (o === "neg") return withExpr(n, () => neg(l));
		const r = ev(right, env);
		if ((o !== "%" || l.t !== "str") && !supportedOperand(r)) throw new PyError(inExpr("Unsupported operator", n), "TypeError");
		const cmp = OPERATOR_TO_CMP[o];
		if (cmp) return withExpr(n, () => bool(compare(l, r, cmp)));
		const bin = OPERATOR_TO_BIN[o];
		return withExpr(n, () => binary(bin, l, r));
	}
	/** Evaluate a tree against the owner's properties; FreeCAD's getPyValue(). */
	function ev(n, env) {
		switch (n.k) {
			case "num": return fromQuantity({
				value: n.v,
				dims: ZERO
			});
			case "const":
				if (n.name === "None") return none;
				if (n.name === "True") return bool(true);
				if (n.name === "False") return bool(false);
				return fromQuantity({
					value: n.v,
					dims: ZERO
				});
			case "unit": return fromQuantity(n.q);
			case "str":
				if (n.bad) throw new PyError(n.bad, "UnicodeDecodeError", "eval", true);
				return str(n.s);
			case "var": return evalVar(n, env);
			case "neg": return calc(n, "neg", n.a, null, env);
			case "pos": return calc(n, "pos", n.a, null, env);
			case "op": return calc(n, n.op, n.l, n.r, env);
			case "cond": return truth(ev(n.c, env)) ? ev(n.t, env) : ev(n.f, env);
			case "range": return rangeList(n, env);
			case "fn": return evalFunction(n, env);
		}
	}
	var CELL = /^(\$?)([A-Z]{1,2})(\$?)([0-9]+)$/;
	function stringToAddress(s) {
		const m = CELL.exec(s);
		if (!m) return null;
		let col = 0;
		for (const ch of m[2]) col = col * 26 + (ch.charCodeAt(0) - 64);
		const row = Number(m[4]);
		return row >= 1 && row <= 16384 && col >= 1 && col <= 702 ? {
			row,
			col
		} : null;
	}
	var columnName = (col) => (col > 26 ? String.fromCharCode(64 + Math.floor((col - 1) / 26)) : "") + String.fromCharCode(65 + (col - 1) % 26);
	function rangeCells(n) {
		const c1 = stringToAddress(n.a), c2 = stringToAddress(n.b);
		if (!c1 || !c2) throw new PyError(inExpr(`Invalid cell range ${n.a}:${n.b}`, n), "ExpressionError");
		const out = [];
		for (let r = Math.min(c1.row, c2.row); r <= Math.max(c1.row, c2.row); r++) for (let c = Math.min(c1.col, c2.col); c <= Math.max(c1.col, c2.col); c++) out.push(`${columnName(c)}${r}`);
		return out;
	}
	function envCells(n, env) {
		const got = env.rangeCells?.(n);
		if (got) return got;
		const out = [];
		for (const addr of rangeCells(n)) if (Object.prototype.hasOwnProperty.call(env.vars, addr)) out.push({
			addr,
			value: env.vars[addr]
		});
		return out;
	}
	function rangeList(n, env) {
		return {
			t: "list",
			v: envCells(n, env).map((c) => propertyValue(c.value))
		};
	}
	var AGGREGATE_KINDS = /* @__PURE__ */ new Set([
		"quantity",
		"float",
		"int"
	]);
	var AGGREGATES = /* @__PURE__ */ new Set([
		"sum",
		"average",
		"stddev",
		"count",
		"min",
		"max",
		"and",
		"or"
	]);
	var asBool = (v) => Math.abs(v) >= 1e-7;
	var qty0 = {
		value: 0,
		dims: ZERO
	};
	/** The collectors of the aggregate functions (Collector and its subclasses in Expression.cpp), fed one value at a time. */
	var Collector = class {
		f;
		q = qty0;
		first = true;
		n = 0;
		mean = qty0;
		m2 = qty0;
		constructor(f) {
			this.f = f;
		}
		collect(v) {
			const f = this.f;
			if (f !== "and" && f !== "or" && this.first) this.q = {
				value: this.q.value,
				dims: v.dims
			};
			switch (f) {
				case "sum":
					this.q = qAddAssign(this.q, v);
					break;
				case "average":
					this.q = qAddAssign(this.q, v);
					this.n++;
					break;
				case "count":
					this.n++;
					break;
				case "min":
					if (this.first || qLess(v, this.q)) this.q = v;
					break;
				case "max":
					if (this.first || qGreater(v, this.q)) this.q = v;
					break;
				case "and":
					if (this.first) this.q = {
						value: asBool(v.value) ? 1 : 0,
						dims: ZERO
					};
					else if (!asBool(v.value)) this.q = {
						value: 0,
						dims: ZERO
					};
					break;
				case "or":
					if (this.first) this.q = {
						value: asBool(v.value) ? 1 : 0,
						dims: ZERO
					};
					else if (asBool(v.value)) this.q = {
						value: 1,
						dims: ZERO
					};
					break;
				case "stddev": {
					if (this.first) {
						this.m2 = {
							value: 0,
							dims: unitMul(v.dims, v.dims)
						};
						this.mean = {
							value: 0,
							dims: v.dims
						};
						this.n = 0;
					}
					const delta = qSub(v, this.mean);
					this.n++;
					this.mean = qAdd(this.mean, qDiv(delta, {
						value: this.n,
						dims: ZERO
					}));
					this.m2 = qAdd(this.m2, qMul(delta, qSub(v, this.mean)));
					break;
				}
			}
			this.first = false;
		}
		result() {
			switch (this.f) {
				case "average": return qDiv(this.q, {
					value: this.n,
					dims: ZERO
				});
				case "count": return {
					value: this.n,
					dims: ZERO
				};
				case "stddev":
					if (this.n < 2) throw new PyError("Invalid number of entries: at least two required.", "ExpressionError");
					return {
						value: qPowQ(qDiv(this.m2, {
							value: this.n - 1,
							dims: ZERO
						}), {
							value: .5,
							dims: ZERO
						}).value,
						dims: this.mean.dims
					};
				default: return this.q;
			}
		}
	};
	/** boost::math::round and trunc (boost/math/special_functions/round.hpp, trunc.hpp): neither takes a value that is not finite. */
	function boostRound(v, name) {
		if (!Number.isFinite(v)) throw new PyError(`Error in function boost::math::${name}<double>(double): Value ${Number.isNaN(v) ? "nan" : v > 0 ? "inf" : "-inf"} can not be represented in the target integer type.`, "FreeCADError");
		if (name === "trunc") return v >= 0 ? Math.floor(v) : Math.ceil(v);
		if (-.5 < v && v < .5) return 0;
		if (v > 0) {
			const c = Math.ceil(v);
			return c - v > .5 ? c - 1 : c;
		}
		const fl = Math.floor(v);
		return v - fl > .5 ? fl + 1 : fl;
	}
	var pi = Math.PI;
	var toRadians = (d) => d * (pi / 180);
	function evalFunction(n, env) {
		const f = n.f, args = n.args;
		const fail = (cls, msg) => {
			throw new PyError(inExpr(msg, n), cls);
		};
		if (AGGREGATES.has(f)) {
			const c = new Collector(f);
			for (const a of args) if (a.k === "range") for (const cell of envCells(a, env)) {
				const q = cell.kind !== void 0 && !AGGREGATE_KINDS.has(cell.kind) ? null : toQuantity(propertyValue(cell.value));
				if (!q) throw new PyError(inExpr("Invalid property type for aggregate.", n), "ExpressionError");
				c.collect(q);
			}
			else {
				const q = toQuantity(ev(a, env));
				if (q) c.collect(q);
			}
			return fromQuantity(c.result());
		}
		if (f === "list" || f === "tuple") {
			if (args.length === 1 && args[0].k === "range") {
				const l = ev(args[0], env);
				if (f === "list") return l;
				return fail("TypeError", `PyCXX: Error creating object of type N2Py5TupleE from ${repr(l)}`);
			}
			return {
				t: f,
				v: args.map((a) => ev(a, env))
			};
		}
		if (args.length === 0) fail("ExpressionError", "Function requires at least one argument.");
		switch (f) {
			case "str": return str(pyStr(ev(args[0], env)));
			case "parsequant": {
				const text = pyStr(ev(args[0], env));
				try {
					return {
						t: "qty",
						q: parseQuantity(text)
					};
				} catch (e) {
					if (e instanceof PyError) throw e;
					if (e instanceof QuantityError) throw new PyError(e.message, e.kind === "mismatch" ? "ArithmeticError" : e.kind === "syntax" ? "ParserError" : "ArithmeticError", e.kind);
					throw e;
				}
			}
			case "hiddenref":
			case "href": return ev(args[0], env);
			case "address": {
				const row = ev(args[0], env), col = ev(args[1], env);
				if (row.t !== "int" && row.t !== "bool") return fail("ExpressionError", "Function requires the first argument to be an integer.");
				if (col.t !== "int" && col.t !== "bool") return fail("ExpressionError", "Function requires the second argument to be an integer.");
				let absRow = true, absCol = true;
				if (args.length > 2) {
					const ref = ev(args[2], env);
					if (ref.t !== "int" && ref.t !== "bool") return fail("ExpressionError", "Function requires the third argument to be an integer.");
					const value = Number(ref.t === "int" ? ref.v : ref.v ? 1n : 0n);
					if (value < 1 || value > 4) return fail("ExpressionError", "Invalid reference type: must be 1, 2, 3, or 4.");
					absRow = value === 1 || value === 2;
					absCol = value === 1 || value === 3;
				}
				const r = Number(row.t === "int" ? row.v : row.v ? 1n : 0n), c = Number(col.t === "int" ? col.v : col.v ? 1n : 0n);
				if (r < 1 || r > 16384 || c < 1 || c > 702) return fail("ExpressionError", "Cell address out of bounds.");
				return str(`${absCol ? "$" : ""}${columnName(c)}${absRow ? "$" : ""}${r}`);
			}
			case "create":
			case "matrix":
			case "placement":
			case "rotation":
			case "vector":
			case "translationm":
			case "minvert":
			case "mrotate":
			case "mrotatex":
			case "mrotatey":
			case "mrotatez":
			case "mscale":
			case "mtranslate":
			case "rotationx":
			case "rotationy":
			case "rotationz":
			case "vangle":
			case "vcross":
			case "vdot":
			case "vlinedist":
			case "vlinesegdist":
			case "vlineproj":
			case "vnormalize":
			case "vplanedist":
			case "vplaneproj":
			case "vscale":
			case "vscalex":
			case "vscaley":
			case "vscalez": return evalObjectFunction(n, env);
		}
		const arg = (i, msg) => {
			const q = toQuantity(ev(args[i], env));
			if (!q) return fail("TypeError", msg);
			return q;
		};
		const v1 = arg(0, "Invalid first argument.");
		const v2 = args.length > 1 ? arg(1, "Invalid second argument.") : null;
		const v3 = args.length > 2 ? arg(2, "Invalid third argument.") : null;
		let value = v1.value;
		let dims = ZERO;
		let scaler = 1;
		const angleOrNone = (q) => isDimless(q.dims) || sameDims(q.dims, ANGLE);
		switch (f) {
			case "cos":
			case "sin":
			case "tan":
				if (!angleOrNone(v1)) return fail("ExpressionError", "Unit must be either empty or an angle.");
				value = toRadians(value);
				break;
			case "acos":
			case "asin":
			case "atan":
				if (!isDimless(v1.dims)) return fail("ExpressionError", "Unit must be empty.");
				dims = ANGLE;
				scaler = 180 / pi;
				break;
			case "exp":
			case "log":
			case "log10":
			case "sinh":
			case "tanh":
			case "cosh":
				if (!isDimless(v1.dims)) return fail("ExpressionError", "Unit must be empty.");
				break;
			case "round":
			case "trunc":
			case "ceil":
			case "floor":
			case "abs":
				dims = v1.dims;
				break;
			case "sqrt":
				dims = unitRoot(v1.dims, 2);
				break;
			case "cbrt":
				dims = unitRoot(v1.dims, 3);
				break;
			case "atan2":
				if (!sameDims(v1.dims, v2.dims)) return fail("ExpressionError", "Units must be equal.");
				dims = ANGLE;
				scaler = 180 / pi;
				break;
			case "mod":
				if (!sameDims(v1.dims, v2.dims) && !isDimless(v1.dims) && !isDimless(v2.dims)) return fail("ExpressionError", "Units must be equal or dimensionless.");
				dims = v1.dims;
				break;
			case "pow": {
				if (!isDimless(v2.dims)) return fail("ExpressionError", "Exponent is not allowed to have a unit.");
				const exponent = v2.value;
				if (!isDimless(v1.dims)) {
					if (exponent - boostRound(exponent, "round") < 1e-9) dims = unitPow(v1.dims, exponent);
					else return fail("ExpressionError", "Exponent must be an integer when used with a unit.");
				}
				break;
			}
			case "hypot":
			case "cath":
				if (!sameDims(v1.dims, v2.dims)) return fail("ExpressionError", "Units must be equal.");
				if (args.length > 2 && !sameDims(v2.dims, v3.dims)) return fail("ExpressionError", "Units must be equal.");
				dims = v1.dims;
				break;
			case "not": break;
			default: return fail("ExpressionError", `Unknown function: ${f}`);
		}
		let output;
		switch (f) {
			case "acos":
				output = Math.acos(value);
				break;
			case "asin":
				output = Math.asin(value);
				break;
			case "atan":
				output = Math.atan(value);
				break;
			case "abs":
				output = Math.abs(value);
				break;
			case "exp":
				output = Math.exp(value);
				break;
			case "log":
				output = Math.log(value);
				break;
			case "log10":
				output = Math.log(value) / Math.log(10);
				break;
			case "sin":
				output = Math.sin(value);
				break;
			case "sinh":
				output = Math.sinh(value);
				break;
			case "tan":
				output = Math.tan(value);
				break;
			case "tanh":
				output = Math.tanh(value);
				break;
			case "sqrt":
				output = Math.sqrt(value);
				break;
			case "cbrt":
				output = Math.cbrt(value);
				break;
			case "cos":
				output = Math.cos(value);
				break;
			case "cosh":
				output = Math.cosh(value);
				break;
			case "mod":
				output = value % v2.value;
				break;
			case "atan2":
				output = Math.atan2(value, v2.value);
				break;
			case "pow":
				output = cpow(value, v2.value);
				break;
			case "hypot":
				output = Math.sqrt(cpow(v1.value, 2) + cpow(v2.value, 2) + (v3 ? cpow(v3.value, 2) : 0));
				break;
			case "cath":
				output = Math.sqrt(cpow(v1.value, 2) - cpow(v2.value, 2) - (v3 ? cpow(v3.value, 2) : 0));
				break;
			case "round":
				output = boostRound(value, "round");
				break;
			case "trunc":
				output = boostRound(value, "trunc");
				break;
			case "ceil":
				output = Math.ceil(value);
				break;
			case "floor":
				output = Math.floor(value);
				break;
			case "not":
				output = asBool(value) ? 0 : 1;
				break;
			default: return fail("ExpressionError", `Unknown function: ${f}`);
		}
		return {
			t: "qty",
			q: {
				value: scaler * output,
				dims
			}
		};
	}
	var NEEDS_GEOMETRY = "Function requires the first argument to be either Matrix, Placement or Rotation.";
	/** What the evaluator does not build: a Matrix, a Placement or a Rotation. (scripts/exprdiff.py excuses the cases where FreeCAD
	*  makes one.) */
	var notBuilt = (n) => new PyError(inExpr("This evaluator does not build a Matrix, a Placement or a Rotation.", n), "NotImplementedError");
	var L_DIMS = [
		1,
		0,
		0,
		0,
		0,
		0,
		0,
		0
	];
	/** PyArg_ParseTuple's "d": a number Python can turn into a float (an int, a float, a bool, a Quantity), else null. */
	function asDouble(v) {
		if (v.t === "float") return v.v;
		if (v.t === "int" || v.t === "bool") {
			const x = Number(v.t === "int" ? v.v : v.v ? 1n : 0n);
			return Number.isFinite(x) ? x : null;
		}
		if (v.t === "qty") return v.q.value;
		return null;
	}
	/** VectorPy::PyInit: three floats (fewer are zeros), a Vector, or a list or tuple of three floats; null where Python raises. */
	function vectorFromArgs(args) {
		if (args.length <= 3) {
			const d = args.map(asDouble);
			if (d.every((x) => x !== null)) return [
				d[0] ?? 0,
				d[1] ?? 0,
				d[2] ?? 0
			];
		}
		if (args.length === 1) {
			const a = args[0];
			if (a.t === "vector") return [...a.v];
			if (a.t === "list" || a.t === "tuple") {
				const d = a.v.map((x) => x.t === "float" ? x.v : x.t === "int" ? Number(x.v) : null);
				if (d.length === 3 && d.every((x) => x !== null)) return d;
			}
		}
		return null;
	}
	/** extractVectorArgument. */
	function vectorArg(n, i, env) {
		const a = ev(n.args[i], env);
		if (a.t !== "vector") throw new PyError(inExpr("Argument must be a vector.", n), "ExpressionError");
		return a.v;
	}
	/** extractLengthValueArgument. */
	function lengthArg(n, i, env) {
		const q = toQuantity(ev(n.args[i], env));
		if (!q) throw new PyError(inExpr("Failed to convert to Quantity.", n), "TypeError");
		if (!isDimless(q.dims) && !sameDims(q.dims, L_DIMS)) throw new PyError(inExpr("Unit must be either empty or a length.", n), "ExpressionError");
		return q.value;
	}
	var toDegrees = (r) => r * (180 / pi);
	var sqr = vecSqr;
	function evalObjectFunction(n, env) {
		const f = n.f, args = n.args;
		const fail = (cls, msg) => {
			throw new PyError(inExpr(msg, n), cls);
		};
		const angleOrNone = (q) => isDimless(q.dims) || sameDims(q.dims, ANGLE);
		switch (f) {
			case "vector": return evalVectorInit(args.map((a) => ev(a, env)));
			case "create": {
				const type = ev(args[0], env);
				if (type.t !== "str") return fail("ExpressionError", "Function requires the first argument to be a string.");
				const name = type.v.toLowerCase();
				if (name !== "matrix" && name !== "vector" && name !== "placement" && name !== "rotation") return fail("ExpressionError", `Unknown type '${type.v}'.`);
				const rest = args.slice(1).map((a) => ev(a, env));
				if (name !== "vector") throw notBuilt(n);
				return rest.length ? evalVectorInit(rest) : vector([
					0,
					0,
					0
				]);
			}
			case "matrix":
			case "placement":
			case "rotation":
				args.forEach((a) => ev(a, env));
				throw notBuilt(n);
			case "minvert":
				ev(args[0], env);
				return fail("ExpressionError", NEEDS_GEOMETRY);
			case "mrotate":
				for (let i = 1; i < args.length; i++) ev(args[i], env);
				ev(args[0], env);
				return fail("ExpressionError", NEEDS_GEOMETRY);
			case "mrotatex":
			case "mrotatey":
			case "mrotatez": {
				const q = toQuantity(ev(args[1], env));
				if (!q) return fail("TypeError", "Invalid rotation angle.");
				if (!angleOrNone(q)) return fail("ExpressionError", "Unit must be either empty or an angle.");
				ev(args[0], env);
				return fail("ExpressionError", NEEDS_GEOMETRY);
			}
			case "mscale":
			case "mtranslate": {
				let values;
				if (args.length === 2) {
					const second = ev(args[1], env);
					const items = sequenceItems(second);
					if (!items) return fail("ExpressionError", `Second parameter is not a sequence type: '${pyStr(second)}'.`);
					if (items.length !== 3) return fail("ExpressionError", `Second parameter provided has ${items.length} elements instead of 3.`);
					values = items;
				} else values = [
					ev(args[1], env),
					ev(args[2], env),
					ev(args[3], env)
				];
				if (!values.every((x) => asDouble(x) !== null)) return fail("ExpressionError", "Error parsing scale values.");
				ev(args[0], env);
				return fail("ExpressionError", NEEDS_GEOMETRY);
			}
			case "translationm":
				if (args.length === 1) {
					const p = ev(args[0], env);
					const items = sequenceItems(p);
					if (!items) return fail("ExpressionError", `Not sequence type: '${pyStr(p)}'.`);
					if (items.length !== 3) return fail("ExpressionError", `Sequence provided has ${items.length} elements instead of 3.`);
					if (!items.every((x) => asDouble(x) !== null)) return fail("ExpressionError", "Error parsing sequence.");
					throw notBuilt(n);
				}
				if (!args.map((a, i) => {
					const q = toQuantity(ev(a, env));
					if (!q) return fail("TypeError", `Invalid ${[
						"first",
						"second",
						"third"
					][i]} argument.`);
					return q;
				}).every((q) => isDimless(q.dims) || sameDims(q.dims, L_DIMS))) return fail("ExpressionError", "Translation units must be a length or dimensionless.");
				throw notBuilt(n);
			case "rotationx":
			case "rotationy":
			case "rotationz": {
				const q = toQuantity(ev(args[0], env));
				if (!q) return fail("TypeError", "Invalid first argument.");
				if (!angleOrNone(q)) return fail("ExpressionError", "Unit must be either empty or an angle.");
				throw notBuilt(n);
			}
		}
		const v1 = vectorArg(n, 0, env);
		switch (f) {
			case "vnormalize": {
				const len = vecLength(v1);
				return vector(len !== 0 && len !== 1 ? [
					v1[0] / len,
					v1[1] / len,
					v1[2] / len
				] : [...v1]);
			}
			case "vscale": return vector([
				v1[0] * lengthArg(n, 1, env),
				v1[1] * lengthArg(n, 2, env),
				v1[2] * lengthArg(n, 3, env)
			]);
			case "vscalex": return vector([
				v1[0] * lengthArg(n, 1, env),
				v1[1],
				v1[2]
			]);
			case "vscaley": return vector([
				v1[0],
				v1[1] * lengthArg(n, 1, env),
				v1[2]
			]);
			case "vscalez": return vector([
				v1[0],
				v1[1],
				v1[2] * lengthArg(n, 1, env)
			]);
		}
		const v2 = vectorArg(n, 1, env);
		switch (f) {
			case "vangle": {
				const len1 = vecLength(v1), len2 = vecLength(v2);
				let angle;
				if (len1 <= Number.EPSILON || len2 <= Number.EPSILON) angle = NaN;
				else {
					let dot = vecDot(v1, v2);
					dot /= len1;
					dot /= len2;
					angle = dot <= -1 ? pi : dot >= 1 ? 0 : Math.acos(dot);
				}
				return {
					t: "qty",
					q: {
						value: toDegrees(angle),
						dims: ANGLE
					}
				};
			}
			case "vcross": return vector(vecCross(v1, v2));
			case "vdot": return float(vecDot(v1, v2));
		}
		const v3 = vectorArg(n, 2, env);
		switch (f) {
			case "vlinedist": return {
				t: "qty",
				q: {
					value: Math.abs(vecLength(vecCross(v3, vecSub(v1, v2))) / vecLength(v3)),
					dims: L_DIMS
				}
			};
			case "vlinesegdist": {
				const len2 = sqr(vecSub(v2, v3));
				if (len2 === 0) return vector([...v2]);
				const p2p1 = vecSub(v3, v2), pXp1 = vecSub(v1, v2);
				const q = vecDot(pXp1, p2p1) / len2;
				return vector(vecSub(vecScale(p2p1, q < 0 ? 0 : 1 < q ? 1 : q), pXp1));
			}
			case "vlineproj": return vector(vecSub(vecScale(v3, vecDot(v2, v3) / sqr(v3)), v2));
			case "vplanedist": return {
				t: "qty",
				q: {
					value: vecDot(vecSub(v1, v2), v3) / vecLength(v3),
					dims: L_DIMS
				}
			};
			case "vplaneproj": return vector(vecSub(v1, vecScale(v3, vecDot(vecSub(v1, v2), v3) / sqr(v3))));
		}
		return fail("ExpressionError", `Unknown function: ${f}`);
	}
	function evalVectorInit(args) {
		const v = vectorFromArgs(args);
		if (!v) throw systemError();
		return vector(v);
	}
	/** The items of a sequence Python can iterate (a str, a list, a tuple or a Vector), else null. */
	function sequenceItems(v) {
		if (v.t === "str") return Array.from(v.v).map((c) => str(c));
		if (v.t === "list" || v.t === "tuple") return v.v;
		if (v.t === "vector") return v.v.map((x) => float(x));
		return null;
	}
	/** The result as a quantity: a number, a Quantity or a bool; anything else is not a quantity (expressionFromPy gives a
	*  StringExpression or a PyObjectExpression for it, and interpretQuantityInput refuses those). */
	function asQuantity(v) {
		switch (v.t) {
			case "qty": return v.q;
			case "float": return {
				value: v.v,
				dims: ZERO
			};
			case "int": return {
				value: Number(v.v),
				dims: ZERO
			};
			case "bool": return {
				value: v.v ? 1 : 0,
				dims: ZERO
			};
			default: throw new QuantityError("Expression could not be evaluated", "eval");
		}
	}
	/** A tree nested deeper than the JavaScript stack (thousands of signs or brackets) stops with the error Python gives for it,
	*  not the engine's own. */
	function deep(f) {
		try {
			return f();
		} catch (e) {
			if (e instanceof RangeError && /call stack/i.test(e.message)) throw new PyError("maximum recursion depth exceeded", "RecursionError");
			throw e;
		}
	}
	/** Evaluate an expression (without its leading "=") to a Python value. */
	function evaluateValue(text, env) {
		return deep(() => ev(parseExpr(text, new Set(Object.keys(env.vars)), env.owner), env));
	}
	//#endregion
	//#region scripts/expr-server-entry.ts
	var g = globalThis;
	if (typeof g.TextEncoder === "undefined") {
		g.TextEncoder = class {
			encode(s) {
				const bin = unescape(encodeURIComponent(s.toWellFormed()));
				return Uint8Array.from(bin, (c) => c.charCodeAt(0));
			}
		};
		g.TextDecoder = class {
			decode(b) {
				try {
					return decodeURIComponent(Array.from(b, (x) => "%" + x.toString(16).padStart(2, "0")).join(""));
				} catch {
					throw new TypeError("The encoded data was not valid for encoding utf-8");
				}
			}
		};
	}
	var replacer = (_k, v) => {
		if (typeof v === "bigint") return { $i: v.toString() };
		if (typeof v === "number" && (!Number.isFinite(v) || Object.is(v, -0))) return { $f: Number.isNaN(v) ? "nan" : v === Infinity ? "inf" : v === -Infinity ? "-inf" : "-0" };
		return v;
	};
	var reviver = (_k, v) => {
		if (v && typeof v === "object" && !Array.isArray(v)) {
			const o = v;
			if (typeof o.$i === "string" && Object.keys(o).length === 1) return BigInt(o.$i);
			if (typeof o.$f === "string" && Object.keys(o).length === 1) return o.$f === "nan" ? NaN : o.$f === "inf" ? Infinity : o.$f === "-inf" ? -Infinity : -0;
		}
		return v;
	};
	var decode = (text) => JSON.parse(text, reviver);
	var encode = (x) => JSON.stringify(x, replacer);
	function fail(e) {
		if (e instanceof PyError) return {
			error: e.message,
			etype: e.etype,
			kind: e.kind
		};
		if (e instanceof QuantityError) return {
			error: e.message,
			etype: "QuantityError",
			kind: e.kind
		};
		if (e instanceof RangeError && /call stack/i.test(e.message)) return {
			error: "maximum recursion depth exceeded",
			etype: "RecursionError",
			kind: "eval"
		};
		return {
			error: `${e.name}: ${e.message}`,
			etype: "Crash",
			kind: "eval"
		};
	}
	var guard = (f) => {
		try {
			return encode({ ok: f() });
		} catch (e) {
			return encode(fail(e));
		}
	};
	/** A path whose `Name.prop` the caller decides after the parse (its resolveAmbiguity runs in Python): it reads as expr.ts's
	*  own default meanwhile, and `amb` says what was written and how many of the names are the default's. */
	var deferred = (obj, prop, owner) => {
		const names = obj.name === owner ? [prop] : [obj.name, prop];
		return {
			doc: null,
			obj: null,
			local: false,
			names,
			sub: [],
			amb: {
				obj,
				prop,
				n: names.length
			}
		};
	};
	/** The env Python sends: the owner's properties the tree reads, and per path (by its `id`) and range what the document
	*  resolved, or the error it raised there. */
	function env(j) {
		const resolved = j.resolved ?? {}, ranges = j.ranges ?? {};
		const thrown = (r) => new PyError(r.error, r.etype, r.kind ?? "eval");
		return {
			vars: j.vars ?? {},
			owner: j.owner ?? void 0,
			doc: j.doc ?? void 0,
			resolve: (p) => {
				const r = resolved[p.id ?? -1];
				if (!r) return null;
				if (r.error !== void 0) throw thrown(r);
				return {
					value: r.value,
					rest: r.rest
				};
			},
			rangeCells: (n) => {
				const r = ranges[n.id ?? -1];
				if (!r) return null;
				if (!Array.isArray(r)) throw thrown(r);
				return r;
			}
		};
	}
	globalThis.FCExpr = {
		parse: (text, names, owner, defer) => guard(() => parseExpr(text, new Set(names), owner ?? void 0, defer ? deferred : void 0)),
		toText: (node) => guard(() => toText(decode(node))),
		evaluate: (node, e) => guard(() => ev(decode(node), env(decode(e)))),
		evaluateText: (text, e) => guard(() => evaluateValue(text, env(decode(e)))),
		parseUnit: (text) => guard(() => parseUnit(text)),
		isTokenAUnit: (s) => guard(() => isTokenAUnit(s)),
		isTokenAConstant: (s) => guard(() => isTokenAConstant(s)),
		pyStr: (v) => guard(() => pyStr(decode(v))),
		userString: (q, schema, decimals, denominator) => guard(() => {
			const r = userString(decode(q), schema ?? void 0, decimals ?? void 0, denominator ?? void 0);
			return [
				r.text,
				r.factor,
				r.unit
			];
		}),
		toNumber: (v, format, precision) => guard(() => toNumber(decode(v), format, precision)),
		setInt32Cast: (on) => {
			QUIRKS.int32Cast = on;
			return encode({ ok: true });
		}
	};
	//#endregion
})();
