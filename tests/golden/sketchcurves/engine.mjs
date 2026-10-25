//#region ui/src/units-data.ts
/** Each token the quantity lexer knows: its value in internal units and its dimensions. */
const UNITS = {
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
[...[
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
const FUNCS = {
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
const DEAD = [
	"atan2",
	"mod",
	"pow"
];
[
	...Object.keys(UNITS),
	...Object.keys(FUNCS),
	...DEAD
];
//#endregion
//#region ui/src/sketchcurves.ts
const isConic = (g) => !!g && (g.type === "Ellipse" || g.type === "ArcOfEllipse" || g.type === "ArcOfHyperbola" || g.type === "ArcOfParabola");
const sub$1 = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add$1 = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mul$1 = (a, k) => [a[0] * k, a[1] * k];
const len$1 = (a) => Math.hypot(a[0], a[1]);
const unit = (a) => {
	const l = len$1(a);
	return l ? [a[0] / l, a[1] / l] : [1, 0];
};
/** The conic's X direction (Part's XAxis: the major axis, towards a parabola's focus) and Y = Z ^ X. */
function conicAxes(g) {
	const x = unit(g.x_axis ?? [1, 0]);
	return {
		x,
		y: [-x[1], x[0]]
	};
}
/** ElCLib's EllipseValue / HyperbolaValue / ParabolaValue: the conic at parameter u. */
function conicValue(g, u) {
	const { x, y } = conicAxes(g);
	let a1, a2;
	if (g.type === "ArcOfHyperbola") {
		a1 = g.major_radius * Math.cosh(u);
		a2 = g.minor_radius * Math.sinh(u);
	} else if (g.type === "ArcOfParabola") {
		a1 = g.focal === 0 ? 0 : u * u / (4 * g.focal);
		a2 = u;
	} else {
		a1 = g.major_radius * Math.cos(u);
		a2 = g.minor_radius * Math.sin(u);
	}
	return [a1 * x[0] + a2 * y[0] + g.center[0], a1 * x[1] + a2 * y[1] + g.center[1]];
}
/** The conic's first derivative at u. */
function conicTangent(g, u) {
	const { x, y } = conicAxes(g);
	let a1, a2;
	if (g.type === "ArcOfHyperbola") {
		a1 = g.major_radius * Math.sinh(u);
		a2 = g.minor_radius * Math.cosh(u);
	} else if (g.type === "ArcOfParabola") {
		a1 = g.focal === 0 ? 0 : u / (2 * g.focal);
		a2 = 1;
	} else {
		a1 = -g.major_radius * Math.sin(u);
		a2 = g.minor_radius * Math.cos(u);
	}
	return [a1 * x[0] + a2 * y[0], a1 * x[1] + a2 * y[1]];
}
/** The parameter range: [0, 2π] for an ellipse, the trim of an arc. */
function conicRange(g) {
	return g.type === "Ellipse" ? [0, 2 * Math.PI] : [g.start_angle, g.end_angle];
}
/** An ellipse's or hyperbola's first focus (on the X axis), a parabola's focus. */
function focus1(g) {
	const { x } = conicAxes(g);
	if (g.type === "ArcOfParabola") return add$1(g.center, mul$1(x, g.focal));
	const a = g.major_radius, b = g.minor_radius;
	const d = g.type === "ArcOfHyperbola" ? Math.sqrt(a * a + b * b) : Math.sqrt(Math.max(0, a * a - b * b));
	return add$1(g.center, mul$1(x, d));
}
/** The knot sequence with each knot repeated by its multiplicity, padded at both ends for a periodic curve as
*  GCS::BSpline::setupFlattenedKnots pads it. */
function flatKnots(b) {
	const fk = [];
	b.knots.forEach((k, i) => {
		for (let m = 0; m < b.mults[i]; m++) fk.push(k);
	});
	if (b.periodic) {
		const period = b.knots[b.knots.length - 1] - b.knots[0], c = b.degree + 1 - b.mults[0];
		const front = fk.slice(fk.length - b.mults[b.mults.length - 1] - c, fk.length - b.mults[b.mults.length - 1]).map((k) => k - period);
		const back = fk.slice(b.mults[0], b.mults[0] + c).map((k) => k + period);
		return [
			...front,
			...fk,
			...back
		];
	}
	return fk;
}
/** Geom_BSplineCurve::FirstParameter and LastParameter. */
function bsplineRange(b) {
	if (b.periodic) return [b.knots[0], b.knots[b.knots.length - 1]];
	const fk = flatKnots(b);
	return [fk[b.degree], fk[fk.length - 1 - b.degree]];
}
const weightsOf = (b) => b.weights && b.weights.length === b.poles.length ? b.weights : b.poles.map(() => 1);
/** The B-spline at u and its first derivative: de Boor on the homogeneous poles of the knot span holding u. */
function bsplineD1(b, u) {
	const p = b.degree, fk = flatKnots(b), n = b.poles.length, w = weightsOf(b);
	let k = p;
	while (k + 1 < fk.length - p - 1 && fk[k + 1] <= u) k++;
	const start = k - p;
	const at = (i) => (start + i) % n;
	const spline = (deg, d) => {
		for (let r = 1; r <= deg; r++) for (let j = deg; j > r - 1; j--) {
			const alpha = (u - fk[j + k - deg]) / (fk[j + 1 + k - r] - fk[j + k - deg]);
			d[j] = (1 - alpha) * d[j - 1] + alpha * d[j];
		}
		return deg < d.length ? d[deg] : 0;
	};
	const vals = (f) => spline(p, Array.from({ length: p + 1 }, (_, i) => f(at(i))));
	const xs = vals((i) => b.poles[i][0] * w[i]), ys = vals((i) => b.poles[i][1] * w[i]), ws = vals((i) => w[i]);
	const slope = (f) => p * spline(p - 1, Array.from({ length: p }, (_, j) => {
		const i = j + 1;
		return (f(at(i)) - f(at(i - 1))) / (fk[start + i + p] - fk[start + i]);
	}));
	const xd = slope((i) => b.poles[i][0] * w[i]), yd = slope((i) => b.poles[i][1] * w[i]), wd = slope((i) => w[i]);
	return {
		p: [xs / ws, ys / ws],
		d: [(ws * xd - wd * xs) / ws / ws, (ws * yd - wd * ys) / ws / ws]
	};
}
const bsplineValue = (b, u) => bsplineD1(b, u).p;
/** Geom_BSplineCurve::StartPoint / EndPoint: the end pole of a clamped curve, else the curve at its end parameter. */
function bsplineStart(b) {
	return b.mults[0] === b.degree + 1 ? b.poles[0] : bsplineValue(b, bsplineRange(b)[0]);
}
function bsplineEnd(b) {
	return b.mults[b.mults.length - 1] === b.degree + 1 ? b.poles[b.poles.length - 1] : bsplineValue(b, bsplineRange(b)[1]);
}
/** A curve's parameterisation, for the curves here (a line by length, a circle by angle, as OpenCascade's). */
function parameterised(g) {
	switch (g.type) {
		case "LineSegment": {
			const d = unit(sub$1(g.end, g.start));
			return {
				range: [0, len$1(sub$1(g.end, g.start))],
				at: (u) => add$1(g.start, mul$1(d, u)),
				tangent: () => d
			};
		}
		case "Circle":
		case "ArcOfCircle": {
			const r = g.radius, c = g.center;
			return {
				range: g.type === "Circle" ? [0, 2 * Math.PI] : [g.start_angle, g.end_angle],
				at: (u) => [c[0] + r * Math.cos(u), c[1] + r * Math.sin(u)],
				tangent: (u) => [-r * Math.sin(u), r * Math.cos(u)]
			};
		}
		case "Ellipse":
		case "ArcOfEllipse":
		case "ArcOfHyperbola":
		case "ArcOfParabola": return {
			range: conicRange(g),
			at: (u) => conicValue(g, u),
			tangent: (u) => conicTangent(g, u)
		};
		case "BSplineCurve": return {
			range: bsplineRange(g),
			at: (u) => bsplineValue(g, u),
			tangent: (u) => bsplineD1(g, u).d
		};
		default: return null;
	}
}
/** GeomCurve::closestParameter: the nearest orthogonal projection of p within the curve's range (the roots of
*  (C(u) - p)·C'(u), bracketed on a sampling and halved to the bit); without one, the nearer end. */
function closestParameter(g, p) {
	const c = parameterised(g);
	if (!c) return null;
	const [u0, u1] = c.range;
	const f = (u) => {
		const q = c.at(u), t = c.tangent(u);
		return (q[0] - p[0]) * t[0] + (q[1] - p[1]) * t[1];
	};
	const d2 = (u) => {
		const q = c.at(u);
		return (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2;
	};
	const n = g.type === "LineSegment" ? 1 : g.type === "BSplineCurve" ? 32 * g.poles.length : 64;
	let best = null, bestD = Infinity;
	const consider = (u) => {
		const d = d2(u);
		if (d < bestD) {
			bestD = d;
			best = u;
		}
	};
	let ua = u0, fa = f(u0);
	for (let i = 1; i <= n; i++) {
		const ub = i === n ? u1 : u0 + (u1 - u0) * i / n, fb = f(ub);
		if (fa === 0) consider(ua);
		else if (fa < 0 !== fb < 0 && fb !== 0) {
			let lo = ua, hi = ub, flo = fa;
			for (let it = 0; it < 200; it++) {
				const mid = lo + (hi - lo) / 2;
				if (mid <= lo || mid >= hi) break;
				const fm = f(mid);
				if (fm === 0) {
					lo = hi = mid;
					break;
				}
				if (fm < 0 === flo < 0) {
					lo = mid;
					flo = fm;
				} else hi = mid;
			}
			consider(Math.abs(f(lo)) <= Math.abs(f(hi)) ? lo : hi);
		}
		ua = ub;
		fa = fb;
	}
	if (fa === 0) consider(ua);
	if (best !== null) return best;
	return d2(u1) < d2(u0) ? u1 : u0;
}
/** SketchObject::exposeInternalGeometry(GeoId): the internal geometry of the conic or B-spline geoId that the sketch's
*  InternalAlignment constraints do not already have, numbered from firstNew (getHighestCurveIndex() + 1). */
function exposeInternalGeometry$1(geometry, existing, geoId, isWeighted) {
	const g = geometry[geoId];
	const out = {
		geometry: [],
		alignments: [],
		others: [],
		order: []
	};
	if (!g) return null;
	const have = existing.filter((c) => c.second === geoId);
	const has = (a) => have.some((c) => c.alignment === a);
	let next = geometry.length;
	const line = (a, b) => ({
		type: "LineSegment",
		start: a,
		end: b,
		construction: true
	});
	const point = (a) => ({
		type: "Point",
		at: a,
		construction: true
	});
	const align = (geo, firstPos, alignment, index = -1) => {
		out.geometry.push(geo);
		out.order.push(out.alignments.length);
		out.alignments.push({
			first: next++,
			firstPos,
			second: geoId,
			alignment,
			index
		});
	};
	if (g.type === "Ellipse" || g.type === "ArcOfEllipse") {
		if (have.some((c) => ![
			"EllipseMajorDiameter",
			"EllipseMinorDiameter",
			"EllipseFocus1",
			"EllipseFocus2"
		].includes(c.alignment))) return null;
		const c = g.center, a = g.major_radius, b = g.minor_radius, { x } = conicAxes(g), y = [-x[1], x[0]];
		const df = Math.sqrt(a * a - b * b);
		if (!has("EllipseMajorDiameter")) align(line(add$1(c, mul$1(x, a)), sub$1(c, mul$1(x, a))), 0, "EllipseMajorDiameter");
		if (!has("EllipseMinorDiameter")) align(line(add$1(c, mul$1(y, b)), sub$1(c, mul$1(y, b))), 0, "EllipseMinorDiameter");
		if (!has("EllipseFocus1")) align(point(add$1(c, mul$1(x, df))), 1, "EllipseFocus1");
		if (!has("EllipseFocus2")) align(point(sub$1(c, mul$1(x, df))), 1, "EllipseFocus2");
		return out;
	}
	if (g.type === "ArcOfHyperbola") {
		if (have.some((c) => ![
			"HyperbolaMajor",
			"HyperbolaMinor",
			"HyperbolaFocus"
		].includes(c.alignment))) return null;
		const c = g.center, a = g.major_radius, b = g.minor_radius, { x } = conicAxes(g), y = [-x[1], x[0]];
		const majP = add$1(c, mul$1(x, a)), majN = sub$1(c, mul$1(x, a));
		if (!has("HyperbolaMajor")) align(line(majP, majN), 0, "HyperbolaMajor");
		if (!has("HyperbolaMinor")) align(line(add$1(majP, mul$1(y, b)), sub$1(majP, mul$1(y, b))), 0, "HyperbolaMinor");
		if (!has("HyperbolaFocus")) align(point(add$1(c, mul$1(x, Math.sqrt(a * a + b * b)))), 1, "HyperbolaFocus");
		return out;
	}
	if (g.type === "ArcOfParabola") {
		if (have.some((c) => !["ParabolaFocus", "ParabolaFocalAxis"].includes(c.alignment))) return null;
		const f = focus1(g);
		if (!has("ParabolaFocus")) align(point(f), 1, "ParabolaFocus");
		if (!has("ParabolaFocalAxis")) align(line(g.center, f), 0, "ParabolaFocalAxis");
		return out;
	}
	if (g.type === "BSplineCurve") {
		if (have.some((c) => c.alignment !== "BSplineControlPoint" && c.alignment !== "BSplineKnotPoint")) return null;
		const poles = g.poles, w = weightsOf(g);
		const cp = poles.map((_, i) => have.find((c) => c.alignment === "BSplineControlPoint" && c.index === i)?.first ?? null);
		const kp = g.knots.map((_, i) => have.find((c) => c.alignment === "BSplineKnotPoint" && c.index === i)?.first ?? null);
		let firstWeighted = cp[0] !== null && isWeighted(cp[0]);
		const r = len$1(sub$1(poles[1], poles[0])) / 6;
		for (let i = 0; i < poles.length; i++) {
			if (cp[i] !== null) continue;
			const id = next;
			align({
				type: "Circle",
				center: poles[i],
				radius: r,
				construction: true
			}, 3, "BSplineControlPoint", i);
			if (i === 0) {
				cp[0] = id;
				if (w[0] === 1) {
					out.order.push(-1 - out.others.length);
					out.others.push({
						type: "Weight",
						first: id,
						value: w[0]
					});
					firstWeighted = true;
				}
				continue;
			}
			if (firstWeighted && w[0] === w[i]) {
				out.order.push(-1 - out.others.length);
				out.others.push({
					type: "Equal",
					first: id,
					second: cp[0]
				});
			}
		}
		for (let i = 0; i < g.knots.length; i++) {
			if (kp[i] !== null) continue;
			align(point(bsplineValue(g, g.knots[i])), 1, "BSplineKnotPoint", i);
		}
		return out;
	}
	return null;
}
/** Sketcher::GeoEnum: GeoUndef, and the axes (the horizontal one's start is the root point). */
const GEO_UNDEF = -2e3;
function constraint(type, first, firstPos = 0, second = GEO_UNDEF, secondPos = 0, third = GEO_UNDEF, thirdPos = 0, value = 0) {
	return {
		type,
		first,
		firstPos,
		second,
		secondPos,
		third,
		thirdPos,
		value,
		driving: true,
		active: true,
		name: "",
		labelDistance: 10,
		labelPosition: type === "Radius" || type === "Diameter" ? 10 : 0,
		virtual: false
	};
}
const DIMENSIONAL$1 = [
	"Distance",
	"DistanceX",
	"DistanceY",
	"Radius",
	"Diameter",
	"Angle",
	"SnellsLaw",
	"Weight"
];
/** Constraint::isDimensional. */
const isDimensional = (c) => DIMENSIONAL$1.includes(c.type);
/** Sketcher.Constraint(type, *args, value): ConstraintPyImp.cpp's argument forms, the value left out. */
function toArgs(c) {
	const { type: t, first: f, firstPos: fp, second: s, secondPos: sp, third: th, thirdPos: tp } = c;
	switch (t) {
		case "Coincident": return [
			f,
			fp,
			s,
			sp
		];
		case "Horizontal":
		case "Vertical": return s === -2e3 ? [f] : [
			f,
			fp,
			s,
			sp
		];
		case "Parallel":
		case "Equal": return [f, s];
		case "Perpendicular":
		case "Tangent":
			if (th !== -2e3) return [
				f,
				s,
				th,
				tp
			];
			if (fp === 0 && sp === 0) return [f, s];
			if (sp === 0) return [
				f,
				fp,
				s
			];
			return [
				f,
				fp,
				s,
				sp
			];
		case "PointOnObject": return [
			f,
			fp,
			s
		];
		case "Distance":
		case "DistanceX":
		case "DistanceY":
			if (s === -2e3) return fp === 0 ? [f] : [f, fp];
			if (fp === 0 && sp === 0) return [f, s];
			if (sp === 0) return [
				f,
				fp,
				s
			];
			return [
				f,
				fp,
				s,
				sp
			];
		case "Radius":
		case "Diameter":
		case "Weight":
		case "Block": return [f];
		case "Angle":
			if (s === -2e3) return [f];
			if (th !== -2e3) return [
				f,
				s,
				th,
				tp
			];
			if (fp === 0 && sp === 0) return [f, s];
			return [
				f,
				fp,
				s,
				sp
			];
		case "Symmetric": return tp === 0 ? [
			f,
			fp,
			s,
			sp,
			th
		] : [
			f,
			fp,
			s,
			sp,
			th,
			tp
		];
		default: return [
			f,
			fp,
			s,
			sp,
			th,
			tp
		];
	}
}
/** The forms ConstraintPy::PyInit takes an InternalAlignment in: (Geo, Geo) for an axis, (Geo, Pos, Geo) for a focus,
*  (Geo, Pos, Geo, index) for a pole or a knot. */
const ALIGN_TWO = [
	"EllipseMajorDiameter",
	"EllipseMinorDiameter",
	"HyperbolaMajor",
	"HyperbolaMinor",
	"ParabolaFocalAxis"
];
const ALIGN_INDEXED = ["BSplineControlPoint", "BSplineKnotPoint"];
function alignmentArgs(c) {
	const a = c.alignment;
	if (ALIGN_TWO.includes(a)) return [c.first, c.second];
	if (ALIGN_INDEXED.includes(a)) return [
		c.first,
		c.firstPos,
		c.second,
		c.alignmentIndex ?? -1
	];
	return [
		c.first,
		c.firstPos,
		c.second
	];
}
/** Sketcher::Constraint for an InternalAlignment. */
function alignmentConstraint(alignment, first, firstPos, second, index = -1) {
	return {
		...constraint("InternalAlignment", first, firstPos, second),
		alignment,
		alignmentIndex: index
	};
}
function toCons(c) {
	if (c.type === "InternalAlignment" && c.alignment) return {
		type: `InternalAlignment:${c.alignment}`,
		args: alignmentArgs(c)
	};
	const out = {
		type: c.type,
		args: toArgs(c)
	};
	if (isDimensional(c)) out.value = c.value;
	if (!c.driving) out.driving = false;
	if (c.name) out.name = c.name;
	return out;
}
/** ConstraintPy::PyInit's parsing, for the forms toArgs writes (an int argument where the value would be a GeoId). */
function fromCons(k) {
	if (k.type.startsWith("InternalAlignment:")) {
		const al = k.type.slice(18), a = k.args;
		if (ALIGN_TWO.includes(al)) return alignmentConstraint(al, a[0], 0, a[1]);
		if (ALIGN_INDEXED.includes(al)) return alignmentConstraint(al, a[0], a[1], a[2], a[3] ?? -1);
		return alignmentConstraint(al, a[0], a[1], a[2]);
	}
	const t = k.type, a = k.args, v = k.value ?? 0, P = (n) => n;
	let c;
	const hasValue = k.value !== void 0;
	if (t === "Coincident") c = constraint(t, a[0], P(a[1]), a[2], P(a[3]));
	else if (t === "Symmetric") c = constraint(t, a[0], P(a[1]), a[2], P(a[3]), a[4], P(a[5] ?? 0));
	else if (t === "PointOnObject") c = constraint(t, a[0], P(a[1]), a[2]);
	else if (a.length === 1) c = constraint(t, a[0], 0, GEO_UNDEF, 0, GEO_UNDEF, 0, v);
	else if (a.length === 2) {
		if ((t === "DistanceX" || t === "DistanceY") && hasValue) c = constraint(t, a[0], P(a[1]), GEO_UNDEF, 0, GEO_UNDEF, 0, v);
		else c = constraint(t, a[0], 0, a[1], 0, GEO_UNDEF, 0, v);
	} else if (a.length === 3) c = constraint(t, a[0], P(a[1]), a[2], 0, GEO_UNDEF, 0, v);
	else c = constraint(t, a[0], P(a[1]), a[2], P(a[3]), a[4] ?? -2e3, P(a[5] ?? 0), v);
	if (k.driving === false) c.driving = false;
	if (k.name) c.name = k.name;
	return c;
}
/** SketchObject::getPoint(GeoId, PosId): the axes' start is the origin. */
function getPoint(geo, g, pos) {
	if (g === -1 || g === -2) return pos === 1 ? [0, 0] : null;
	const e = geo[g];
	if (!e) return null;
	switch (e.type) {
		case "Point": return pos === 1 ? e.at : null;
		case "LineSegment": return pos === 1 ? e.start : pos === 2 ? e.end : null;
		case "Circle": return pos === 3 ? e.center : null;
		case "ArcOfCircle":
			if (pos === 3) return e.center;
			if (pos === 1) return [e.center[0] + e.radius * Math.cos(e.start_angle), e.center[1] + e.radius * Math.sin(e.start_angle)];
			if (pos === 2) return [e.center[0] + e.radius * Math.cos(e.end_angle), e.center[1] + e.radius * Math.sin(e.end_angle)];
			return null;
		case "Ellipse": return pos === 3 ? e.center : null;
		case "ArcOfEllipse":
		case "ArcOfHyperbola":
		case "ArcOfParabola":
			if (pos === 3) return e.center;
			if (pos === 1) return conicValue(e, e.start_angle);
			if (pos === 2) return conicValue(e, e.end_angle);
			return null;
		case "BSplineCurve":
			if (pos === 1) return bsplineStart(e);
			if (pos === 2) return bsplineEnd(e);
			return null;
	}
}
/** SketchObject::getCoincidenceGroups / getAllCoincidentPoints: the points the Coincident constraints tie to (g, pos). */
function coincidentPoints(cons, g, pos) {
	const groups = [];
	for (const c of cons) {
		if (c.type !== "Coincident") continue;
		const fi = groups.findIndex((m) => m.get(c.first) === c.firstPos), si = groups.findIndex((m) => m.get(c.second) === c.secondPos);
		if (fi >= 0 && si >= 0) {
			if (fi !== si) {
				groups[si].forEach((v, k) => groups[fi].set(k, v));
				groups.splice(si, 1);
			}
		} else if (fi < 0 && si < 0) groups.push(/* @__PURE__ */ new Map([[c.first, c.firstPos], [c.second, c.secondPos]]));
		else if (fi >= 0) groups[fi].set(c.second, c.secondPos);
		else groups[si].set(c.first, c.firstPos);
	}
	return groups.find((m) => m.get(g) === pos) ?? /* @__PURE__ */ new Map();
}
//#endregion
//#region ui/src/sketchops.ts
const CONFUSION$1 = 1e-7;
const PAPPROXIMATION = 1e-8;
const TWO_PI$1 = 2 * Math.PI;
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const len = (a) => Math.hypot(a[0], a[1]);
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
const dist = (a, b) => len(sub(a, b));
const normalize = (a) => {
	const l = len(a);
	return l ? [a[0] / l, a[1] / l] : a;
};
/** Base::Vector3d::ProjectToLine(p, d): the perpendicular from the line through the origin along d to p, negated
*  (FreeCAD's ProjectToLine gives the vector from p to its foot). */
const projectToLine = (p, d) => {
	const t = dot(p, d) / dot(d, d);
	return sub(mul(d, t), p);
};
const clone = (c) => ({ ...c });
const elements = (c) => [
	[c.first, c.firstPos],
	[c.second, c.secondPos],
	[c.third, c.thirdPos]
];
const involvesGeoId = (c, g) => c.first === g || c.second === g || c.third === g;
const involvesGeoIdAndPosId = (c, g, p) => elements(c).some(([eg, ep]) => eg === g && ep === p);
function substituteIndex(c, from, to) {
	if (c.first === from) c.first = to;
	if (c.second === from) c.second = to;
	if (c.third === from) c.third = to;
}
function substituteIndexAndPos(c, fg, fp, tg, tp) {
	if (c.first === fg && c.firstPos === fp) {
		c.first = tg;
		c.firstPos = tp;
	}
	if (c.second === fg && c.secondPos === fp) {
		c.second = tg;
		c.secondPos = tp;
	}
	if (c.third === fg && c.thirdPos === fp) {
		c.third = tg;
		c.thirdPos = tp;
	}
}
/** SketchObject::getConstraintIndices. */
const constraintIndices = (d, g) => d.constraints.map((c, i) => involvesGeoId(c, g) ? i : -1).filter((i) => i >= 0);
const isClosedCurve = (g) => g.type === "Circle" || g.type === "Ellipse" || g.type === "BSplineCurve" && g.periodic;
function range(g) {
	return parameterised(g).range;
}
const valueAt = (g, u) => parameterised(g).at(u);
/** The kernel of the operation running (trim, split, fillet), for the B-spline steps; without one a B-spline is refused. */
let kernel = null;
function withOpKernel(k, f) {
	const prev = kernel;
	kernel = k ?? null;
	try {
		return f();
	} finally {
		kernel = prev;
	}
}
function needKernel(what) {
	if (!kernel) throw new Error(`${what} a B-spline needs the sketch kernel`);
	return kernel;
}
const plainGeo = (g) => {
	const { construction: _c, start_point: _s, end_point: _e, ...rest } = g;
	return rest;
};
/** GeomCurve::closestParameter: OCCT's for a B-spline (GeomAPI_ProjectPointOnCurve), the port's for the others. */
function closestParam(g, p) {
	if (g.type === "BSplineCurve") return needKernel("Cutting")({
		op: "closest",
		geo: plainGeo(g),
		p
	}).u;
	return closestParameter(g, p);
}
/** ElCLib::AdjustPeriodic with Geom_TrimmedCurve::SetTrim's precision: a periodic trim in [0, 2π). */
function setTrimPeriodic(u1, u2) {
	const preci = Math.min(Math.abs(u2 - u1) / 2, CONFUSION$1 * .01);
	u1 -= Math.floor(u1 / TWO_PI$1) * TWO_PI$1;
	if (TWO_PI$1 - u1 < preci) u1 -= TWO_PI$1;
	u2 -= Math.floor((u2 - u1) / TWO_PI$1) * TWO_PI$1;
	if (u2 - u1 < preci) u2 += TWO_PI$1;
	return [u1, u2];
}
/** GeomCurve::createArc(first, last): the same curve trimmed (a circle or an ellipse becomes its arc). */
function createArc(g, u1, u2) {
	const c = g.construction ? { construction: true } : {};
	switch (g.type) {
		case "LineSegment": return {
			type: "LineSegment",
			start: valueAt(g, u1),
			end: valueAt(g, u2),
			...c
		};
		case "Circle":
		case "ArcOfCircle": {
			const [a, b] = setTrimPeriodic(u1, u2);
			return {
				type: "ArcOfCircle",
				center: g.center,
				radius: g.radius,
				start_angle: a,
				end_angle: b,
				...c
			};
		}
		case "Ellipse":
		case "ArcOfEllipse": {
			const [a, b] = setTrimPeriodic(u1, u2);
			return {
				type: "ArcOfEllipse",
				center: g.center,
				major_radius: g.major_radius,
				minor_radius: g.minor_radius,
				x_axis: g.x_axis,
				start_angle: a,
				end_angle: b,
				...c
			};
		}
		case "ArcOfHyperbola":
		case "ArcOfParabola": {
			const { start_point: _s, end_point: _e, ...rest } = g;
			return {
				...rest,
				start_angle: Math.min(u1, u2),
				end_angle: Math.max(u1, u2)
			};
		}
		case "BSplineCurve": return {
			...needKernel("Cutting")({
				op: "trim",
				geo: plainGeo(g),
				u: u1,
				v: u2
			}).geo,
			...c
		};
		default: throw new Error(`${g.type} cannot be cut here yet`);
	}
}
function curveOf(g) {
	const p = parameterised(g);
	if (!p) return null;
	const out = { ...p };
	if (g.type === "LineSegment") out.line = {
		p: g.start,
		d: normalize(sub(g.end, g.start)),
		infinite: false
	};
	if (g.type === "Circle" || g.type === "ArcOfCircle") out.circle = {
		c: g.center,
		r: g.radius
	};
	return out;
}
function infiniteLine(p, d) {
	return {
		range: [-1e100, 1e100],
		at: (u) => add(p, mul(d, u)),
		tangent: () => d,
		line: {
			p,
			d,
			infinite: true
		}
	};
}
const inRange = (c, u, tol = 1e-9) => u >= c.range[0] - tol && u <= c.range[1] + tol;
/** The angle of a point on a circle, brought into the curve's range when it lies there. */
function angleIn(c, q) {
	let a = Math.atan2(q[1] - c.circle.c[1], q[0] - c.circle.c[0]);
	const [u0, u1] = c.range;
	while (a < u0 - 1e-12) a += TWO_PI$1;
	while (a > u0 + TWO_PI$1) a -= TWO_PI$1;
	return a <= u1 + 1e-12 ? a : null;
}
/** The points where two curves meet, overlaps given by their ends (IntRes2d's segments' first and last points). */
function intersect(a, b) {
	const out = [];
	if (a.line && b.line) {
		const den = cross(a.line.d, b.line.d), qp = sub(b.line.p, a.line.p);
		if (Math.abs(den) < 1e-12) {
			if (Math.abs(cross(qp, a.line.d)) > 1e-9) return [];
			const ta = (q) => dot(sub(q, a.line.p), a.line.d);
			const ends = [];
			for (const u of [b.range[0], b.range[1]]) if (!b.line.infinite) {
				const q = b.at(u);
				if (inRange(a, ta(q))) ends.push(q);
			}
			for (const u of [a.range[0], a.range[1]]) if (!a.line.infinite) {
				const q = a.at(u);
				const tb = dot(sub(q, b.line.p), b.line.d);
				if (inRange(b, tb)) ends.push(q);
			}
			return ends;
		}
		const t = cross(qp, b.line.d) / den, s = cross(qp, a.line.d) / den;
		if (inRange(a, t) && inRange(b, s)) out.push(a.at(t));
		return out;
	}
	if (a.line && b.circle || a.circle && b.line) {
		const [l, c] = a.line ? [a, b] : [b, a];
		const f = sub(l.line.p, c.circle.c), bq = dot(f, l.line.d), disc = bq * bq - (dot(f, f) - c.circle.r ** 2);
		if (disc < -1e-12) return [];
		const ts = Math.abs(disc) <= 1e-14 ? [-bq] : [-bq - Math.sqrt(Math.max(0, disc)), -bq + Math.sqrt(Math.max(0, disc))];
		for (const t of ts) {
			if (!inRange(l, t)) continue;
			const q = l.at(t);
			if (angleIn(c, q) !== null) out.push(q);
		}
		return out;
	}
	if (a.circle && b.circle) {
		const d = dist(a.circle.c, b.circle.c), r1 = a.circle.r, r2 = b.circle.r;
		if (d < 1e-12) {
			if (Math.abs(r1 - r2) > 1e-12) return [];
			const ends = [];
			for (const [x, y] of [[a, b], [b, a]]) for (const u of x.range) {
				const q = x.at(u);
				if (angleIn(y, q) !== null && Math.abs(x.range[1] - x.range[0] - TWO_PI$1) > 1e-12) ends.push(q);
			}
			return ends;
		}
		if (d > r1 + r2 + 1e-12 || d < Math.abs(r1 - r2) - 1e-12) return [];
		const k = (r1 * r1 - r2 * r2 + d * d) / (2 * d), h = Math.sqrt(Math.max(0, r1 * r1 - k * k));
		const ex = mul(sub(b.circle.c, a.circle.c), 1 / d), m = add(a.circle.c, mul(ex, k));
		const pts = h < 1e-12 ? [m] : [[m[0] - h * ex[1], m[1] + h * ex[0]], [m[0] + h * ex[1], m[1] - h * ex[0]]];
		for (const q of pts) if (angleIn(a, q) !== null && angleIn(b, q) !== null) out.push(q);
		return out;
	}
	return intersectNumeric(a, b);
}
/** Two curves' crossings found on polylines of them and refined by Newton's method on C1(u) = C2(v). */
function intersectNumeric(a, b) {
	const sample = (c) => {
		let [u0, u1] = c.range;
		if (c.line?.infinite) {
			u0 = -1e4;
			u1 = 1e4;
		}
		const n = 400, us = Array.from({ length: 401 }, (_, i) => u0 + (u1 - u0) * i / n);
		return {
			us,
			pts: us.map((u) => c.at(u))
		};
	};
	const A = sample(a), B = sample(b), out = [];
	for (let i = 0; i < A.pts.length - 1; i++) for (let j = 0; j < B.pts.length - 1; j++) {
		const p = A.pts[i], r = sub(A.pts[i + 1], p), q = B.pts[j], s = sub(B.pts[j + 1], q);
		const den = cross(r, s);
		if (Math.abs(den) < 1e-18) continue;
		const t = cross(sub(q, p), s) / den, w = cross(sub(q, p), r) / den;
		if (t < -.05 || t > 1.05 || w < -.05 || w > 1.05) continue;
		let u = A.us[i] + t * (A.us[i + 1] - A.us[i]), v = B.us[j] + w * (B.us[j + 1] - B.us[j]);
		let ok = false;
		for (let it = 0; it < 60; it++) {
			const e = sub(a.at(u), b.at(v)), ta = a.tangent(u), tb = b.tangent(v);
			const det = -ta[0] * tb[1] + ta[1] * tb[0];
			if (Math.abs(det) < 1e-300) break;
			const du = (-e[0] * -tb[1] + tb[0] * -e[1]) / det, dv = (ta[0] * -e[1] - -e[0] * ta[1]) / det;
			u += du;
			v += dv;
			if (Math.abs(du) + Math.abs(dv) < 1e-15 * (1 + Math.abs(u) + Math.abs(v))) {
				ok = true;
				break;
			}
		}
		if (!ok && dist(a.at(u), b.at(v)) > 1e-10) continue;
		if (!inRange(a, u) || !inRange(b, v)) continue;
		const x = a.at(u);
		if (!out.some((o) => dist(o, x) < 1e-9)) out.push(x);
	}
	return out;
}
/** The two points around `point` where the curve geoId is cut, and the curves cutting it there: cuttingGeoIds[0]
*  before the picked point, [1] after it (GEO_UNDEF where none). null when nothing cuts it. */
function seekTrimPoints(d, geoId, point, includeSketchAxes = false) {
	const g = d.geometry[geoId];
	if (!g) return null;
	if (kernel && d.geometry.some((x) => x.type === "BSplineCurve")) {
		const r = kernel({
			op: "seek",
			geometry: d.geometry.map(plainGeo),
			id: geoId,
			p: point,
			axes: includeSketchAxes
		}).seek;
		if (!r) return null;
		const n = d.geometry.length;
		const idOf = (i) => i < 0 ? GEO_UNDEF : includeSketchAxes && i === n ? -1 : includeSketchAxes && i === n + 1 ? -2 : i;
		return {
			ids: [idOf(r.ids[0]), idOf(r.ids[1])],
			points: r.points
		};
	}
	const primary = curveOf(g);
	if (!primary) return null;
	const periodic = g.type === "Circle" || g.type === "Ellipse" || g.type === "BSplineCurve" && g.periodic;
	const period = g.type === "BSplineCurve" ? range(g)[1] - range(g)[0] : TWO_PI$1;
	const project = (p) => {
		const u = closestParameter(g, p);
		return {
			u,
			d: dist(primary.at(u), p)
		};
	};
	const picked = project(point).u;
	let i1 = -1, i2 = -1, param1 = -1e10, param2 = 1e10;
	let p1 = [0, 0], p2 = [0, 0];
	const others = [];
	d.geometry.forEach((og, id) => {
		if (id !== geoId) {
			const c = curveOf(og);
			if (c) others.push({
				id,
				curve: c,
				bounded: og
			});
		}
	});
	if (includeSketchAxes) {
		others.push({
			id: d.geometry.length,
			curve: infiniteLine([0, 0], [1, 0]),
			bounded: null
		});
		others.push({
			id: d.geometry.length + 1,
			curve: infiniteLine([0, 0], [0, 1]),
			bounded: null
		});
	}
	for (const o of others) {
		const pts = [];
		if (o.bounded && o.bounded.type !== "Point" && o.bounded.type !== "Circle" && o.bounded.type !== "Ellipse") pts.push(getPoint(d.geometry, o.id, 1), getPoint(d.geometry, o.id, 2));
		pts.push(...intersect(primary, o.curve));
		for (const p of pts) {
			const pr = project(p);
			if (pr.d > CONFUSION$1) continue;
			let param = pr.u;
			if (periodic) {
				param = param - period * Math.ceil((param - picked) / period);
				if (param > param1) {
					param1 = param;
					p1 = p;
					i1 = o.id;
				}
				param -= period;
				if (param < param2) {
					param2 = param;
					p2 = p;
					i2 = o.id;
				}
			} else if (param < picked && param > param1) {
				param1 = param;
				p1 = p;
				i1 = o.id;
			} else if (param > picked && param < param2) {
				param2 = param;
				p2 = p;
				i2 = o.id;
			}
		}
	}
	if (periodic && Math.abs(param2 - param1 - period) < 1e-10) {
		if (param2 - picked >= picked - param1) i2 = -1;
		else i1 = -1;
	}
	if (i1 < 0 && i2 < 0) return null;
	const geoIdOf = (i) => i < 0 ? GEO_UNDEF : includeSketchAxes && i === d.geometry.length ? -1 : includeSketchAxes && i === d.geometry.length + 1 ? -2 : i;
	return {
		ids: [geoIdOf(i1), geoIdOf(i2)],
		points: [p1, p2]
	};
}
/** getDirectlyCoincidentPoints(GeoId, PosId): the point and those a Coincident or an endpoint Tangent ties to it, or
*  nothing when there are none. */
function directlyCoincident(d, g, pos) {
	const out = [[g, pos]];
	for (const c of d.constraints) {
		if (c.type === "Coincident") {
			if (c.first === g && c.firstPos === pos) out.push([c.second, c.secondPos]);
			else if (c.second === g && c.secondPos === pos) out.push([c.first, c.firstPos]);
		}
		if (c.type === "Tangent") {
			if (c.first === g && c.firstPos === pos && (c.secondPos === 1 || c.secondPos === 2)) out.push([c.second, c.secondPos]);
			if (c.second === g && c.secondPos === pos && (c.firstPos === 1 || c.firstPos === 2)) out.push([c.first, c.firstPos]);
		}
	}
	return out.length === 1 ? [] : out;
}
/** SketchObject::transferConstraints. */
function transferConstraints(d, fg, fp, tg, tp, doNotTransformTangencies = false) {
	d.constraints = d.constraints.map((c) => {
		if (c.type === "InternalAlignment") return c;
		if (!involvesGeoIdAndPosId(c, fg, fp) || involvesGeoIdAndPosId(c, tg, tp)) return c;
		const n = clone(c);
		substituteIndexAndPos(n, fg, fp, tg, tp);
		if (c.first < 0 && c.second < 0) return c;
		if (c.type === "Tangent" || c.type === "Perpendicular") {
			if (!doNotTransformTangencies) n.type = "Coincident";
		} else if (c.type === "Angle") return c;
		return n;
	});
}
/** SketchObject::delConstraintOnPoint(geoId, posId, onlyCoincident). */
function delConstraintOnPoint(d, g, pos, onlyCoincident) {
	const vals = d.constraints;
	let rg = GEO_UNDEF, rp = 0;
	const found = vals.find((c) => c.type === "Coincident" && involvesGeoIdAndPosId(c, g, pos));
	if (found) {
		if (found.first === g && found.firstPos === pos) {
			rg = found.second;
			rp = found.secondPos;
		} else {
			rg = found.first;
			rp = found.firstPos;
		}
	}
	const transfer = (c, which) => {
		if (rg === -2e3) return false;
		const gk = which, pk = which === "first" ? "firstPos" : "secondPos";
		if (g !== c[gk] || pos !== c[pk]) return false;
		c[gk] = rg;
		c[pk] = rp;
		return true;
	};
	const out = [];
	for (const c0 of vals) {
		if (!involvesGeoIdAndPosId(c0, g, pos)) {
			if ((c0.type === "Distance" || c0.type === "DistanceX" || c0.type === "DistanceY") && c0.first === g && c0.firstPos === 0 && (pos === 1 || pos === 2)) continue;
			out.push(c0);
			continue;
		}
		const c = clone(c0);
		let keep;
		if (c.type !== "Coincident" && onlyCoincident) keep = true;
		else switch (c.type) {
			case "Coincident":
				if (rg === -2e3 || involvesGeoIdAndPosId(c, rg, rp)) keep = false;
				else {
					substituteIndexAndPos(c, g, pos, rg, rp);
					keep = true;
				}
				break;
			case "Distance":
			case "DistanceX":
			case "DistanceY":
				keep = transfer(c, "first") || transfer(c, "second");
				break;
			case "PointOnObject":
				keep = transfer(c, "first");
				break;
			case "Tangent":
			case "Perpendicular":
			case "Vertical":
			case "Horizontal":
			case "Symmetric":
				keep = false;
				break;
			default: keep = null;
		}
		if (keep ?? true) out.push(keep === true && c.type !== c0.type ? c : c);
	}
	d.constraints = out;
}
/** SketchObject::changeConstraintAfterDeletingGeo: null when the constraint goes with the geometry. */
function afterDeletingGeo(c, deleted) {
	if (involvesGeoId(c, deleted)) return null;
	const n = clone(c);
	const fix = (g) => deleted >= 0 ? g > deleted ? g - 1 : g : g < deleted && g !== -2e3 ? g + 1 : g;
	n.first = fix(n.first);
	n.second = fix(n.second);
	n.third = fix(n.third);
	return n;
}
/** SketchObject::delGeometriesExclusiveList. */
function delGeometriesExclusive(d, ids) {
	const s = [...new Set(ids)].sort((a, b) => a - b);
	if (!s.length) return;
	for (const g of [...s].reverse()) for (const pos of [
		1,
		2,
		3
	]) {
		const list = directlyCoincident(d, g, pos);
		if (list.length > 1) {
			delConstraintOnPoint(d, g, pos, true);
			transferConstraints(d, list[0][0], list[0][1], list[1][0], list[1][1]);
		}
	}
	let cons = d.constraints;
	for (const g of [...s].reverse()) cons = cons.map((c) => afterDeletingGeo(c, g)).filter((c) => !!c);
	d.constraints = cons;
	d.geometry = d.geometry.filter((_, i) => !s.includes(i));
}
/** SketchObject::delGeometries: internal geometry goes with its parent. */
function delGeometries(d, ids) {
	const s = ids.filter((g) => g >= 0);
	for (const c of d.constraints) if (c.type === "InternalAlignment" && s.includes(c.second)) s.push(c.first);
	delGeometriesExclusive(d, s);
}
const hasInternalGeometry = (g) => isConic(g) || g.type === "BSplineCurve";
/** GeomConic or GeomArcOfConic: the curves with a centre (circles and arcs of circle too). */
const hasMid = (g) => isConic(g) || g.type === "Circle" || g.type === "ArcOfCircle";
/** SketchObject::delGeometry(GeoId, IncludeInternalGeometry): a conic or a B-spline takes its internal geometry
*  along (deleteUnusedInternalGeometry with delgeoid). */
function delGeometry(d, g, includeInternal) {
	if (includeInternal && hasInternalGeometry(d.geometry[g])) {
		const internal = d.constraints.filter((c) => c.type === "InternalAlignment" && c.second === g).map((c) => c.first);
		for (const id of [...internal, g].sort((a, b) => b - a)) delGeometriesExclusive(d, [id]);
		return;
	}
	delGeometriesExclusive(d, [g]);
}
/** SketchObject::delConstraints. */
function delConstraints(d, ids) {
	const gone = new Set(ids);
	d.constraints = d.constraints.filter((_, i) => !gone.has(i));
}
const isPointAtPosition = (d, g, pos, p) => {
	const q = getPoint(d.geometry, g, pos);
	return !!q && dist(p, q) < 500 * CONFUSION$1;
};
function transformPreexistingForTrim(d, c, geoId, cutting, cut, newId, newPos) {
	if (cutting === -2e3 || !involvesGeoId(c, cutting) || !involvesGeoIdAndPosId(c, geoId, 0)) return null;
	if (c.type === "PointOnObject") {
		if (isPointAtPosition(d, c.first, c.firstPos, cut)) return {
			...clone(c),
			type: "Coincident",
			second: newId,
			secondPos: newPos
		};
		return null;
	}
	if (c.type === "Tangent" || c.type === "Perpendicular") {
		const n = clone(c);
		substituteIndexAndPos(n, geoId, 0, newId, newPos);
		if (n.firstPos === 0) {
			[n.first, n.second] = [n.second, n.first];
			[n.firstPos, n.secondPos] = [n.secondPos, n.firstPos];
		}
		n.third = GEO_UNDEF;
		n.thirdPos = 0;
		return n;
	}
	return null;
}
function newConstraintAtTrimCut(d, cutting, cutGeo, cutPos, p) {
	if (isPointAtPosition(d, cutting, 1, p)) return constraint("Coincident", cutGeo, cutPos, cutting, 1);
	if (isPointAtPosition(d, cutting, 2, p)) return constraint("Coincident", cutGeo, cutPos, cutting, 2);
	return constraint("PointOnObject", cutGeo, cutPos, cutting);
}
/** findPieceContainingPoint. */
function pieceContaining(d, geo, p, newGeos) {
	let u = closestParam(geo, p);
	for (let i = 0; i < newGeos.length; i++) {
		const [f, l] = range(newGeos[i]);
		if (f - u > PAPPROXIMATION && isClosedCurve(geo)) u += range(geo)[1] - range(geo)[0];
		if (f - u <= PAPPROXIMATION && u - l <= PAPPROXIMATION) return i;
	}
	return null;
}
/** SketchObject::deriveConstraintsForPieces. */
function deriveConstraintsForPieces(d, oldId, newIds, newGeos, con, out, assumeTangency) {
	const geo = d.geometry[oldId];
	let [conId, conPos] = [con.first, con.firstPos];
	if (conId === oldId) [conId, conPos] = [con.second, con.secondPos];
	let toAll = false;
	switch (con.type) {
		case "Horizontal":
		case "Vertical":
		case "Parallel":
			toAll = geo.type === "LineSegment";
			break;
		case "Tangent":
		case "Perpendicular": {
			if (!assumeTangency && geo.type === "LineSegment") {
				toAll = true;
				break;
			}
			const conGeo = d.geometry[conId];
			if (!conGeo || conGeo.type === "Point") return false;
			for (let i = 0; i < newIds.length; i++) {
				const coincident = d.constraints.some((c) => c.type === "Coincident" && involvesGeoId(c, newIds[i]) && involvesGeoId(c, conId));
				let meets = false;
				if (!coincident) {
					const a = curveOf(newGeos[i]), b = curveOf(conGeo);
					meets = !!a && !!b && intersect(a, b).length > 0;
				}
				if (coincident || meets) {
					const t = clone(con);
					substituteIndex(t, oldId, newIds[i]);
					out.push(t);
					return true;
				}
			}
			break;
		}
		case "Angle": {
			const [tg, tp] = [con.third, con.thirdPos];
			if (tg === oldId) {
				const list = directlyCoincident(d, tg, tp);
				if (list.length <= 1) return false;
				const idx = pieceContaining(d, geo, getPoint(d.geometry, tg, tp), newGeos);
				if (idx !== null) {
					const t = clone(con);
					substituteIndexAndPos(t, list[0][0], list[0][1], list[1][0], list[1][1]);
					substituteIndex(t, oldId, newIds[idx]);
					out.push(t);
					return true;
				}
			} else if (tg !== -2e3) {
				const idx = pieceContaining(d, geo, getPoint(d.geometry, tg, tp), newGeos);
				if (idx !== null) {
					const t = clone(con);
					substituteIndex(t, oldId, newIds[idx]);
					out.push(t);
					return true;
				}
				break;
			} else if (newGeos.some((g) => g.type !== "LineSegment")) return false;
			else {
				toAll = true;
				break;
			}
			break;
		}
		case "Distance":
		case "DistanceX":
		case "DistanceY":
		case "Coincident":
		case "PointOnObject": {
			if (con.firstPos === 0 && con.secondPos === 0 && newIds.length > 1) {
				out.push({
					...clone(con),
					first: newIds[0],
					firstPos: 1,
					second: newIds[newIds.length - 1],
					secondPos: 2
				});
				return true;
			}
			if (conId === -2e3) return false;
			const cp = getPoint(d.geometry, conId, conPos);
			if (!cp) return false;
			let u = closestParam(geo, cp);
			for (let i = 0; i < newIds.length; i++) {
				const [f, l] = range(newGeos[i]);
				if (f - u > PAPPROXIMATION && isClosedCurve(geo)) u += range(geo)[1] - range(geo)[0];
				if (f - u <= PAPPROXIMATION && u - l <= PAPPROXIMATION) {
					out.push({
						...clone(con),
						first: conId,
						firstPos: conPos,
						second: newIds[i],
						secondPos: 0
					});
					return true;
				}
			}
			break;
		}
		case "Radius":
		case "Diameter":
		case "Equal": if (hasMid(geo)) {
			const t = clone(con);
			substituteIndex(t, oldId, newIds[0]);
			out.push(t);
		}
	}
	if (!toAll) return false;
	if (assumeTangency) {
		const t = clone(con);
		substituteIndex(t, oldId, newIds[0]);
		out.push(t);
	} else for (const id of newIds) {
		const t = clone(con);
		substituteIndex(t, oldId, id);
		out.push(t);
	}
	return true;
}
/** SketchObject::trim(GeoId, point, includeSketchAxes): true when done. */
function trim(d, geoId, point, includeSketchAxes = false, k) {
	return withOpKernel(k, () => trimIt(d, geoId, point, includeSketchAxes));
}
function trimIt(d, geoId, point, includeSketchAxes) {
	const geo = d.geometry[geoId];
	if (!geo || geo.type === "Point" || d.constraints.some((c) => c.type === "InternalAlignment" && c.first === geoId)) return false;
	const construction = !!geo.construction, closed = isClosedCurve(geo);
	const seek = seekTrimPoints(d, geoId, point, includeSketchAxes);
	if (!seek) {
		delGeometry(d, geoId, true);
		return true;
	}
	const cutting = [...seek.ids], cuts = seek.points;
	const [first, last] = range(geo);
	const c0 = closestParam(geo, cuts[0]), c1 = closestParam(geo, cuts[1]);
	if (!closed && Math.abs(first - c0) < PAPPROXIMATION) cutting[0] = GEO_UNDEF;
	if (!closed && Math.abs(last - c1) < PAPPROXIMATION) cutting[1] = GEO_UNDEF;
	const undefs = cutting.filter((g) => g === GEO_UNDEF).length;
	let params;
	if (undefs === 0 && dist(cuts[0], cuts[1]) < 500 * CONFUSION$1) params = [];
	else {
		params = Array.from({ length: 2 - undefs }, () => [first, last]);
		if (params.length && closed) params.pop();
		if (params.length) {
			if (cutting[0] !== -2e3) params[0][1] = c0;
			if (cutting[1] !== -2e3) params[params.length - 1][0] = c1;
		}
	}
	if (!params.length) {
		delGeometry(d, geoId, true);
		return true;
	}
	const newIds = params.length === 1 ? [geoId] : [geoId, d.geometry.length];
	const newGeos = params.map(([a, b]) => createArc(geo, a, b));
	let oldIds = constraintIndices(d, geoId);
	if (!closed) oldIds = oldIds.filter((i) => {
		const c = d.constraints[i];
		const s = involvesGeoIdAndPosId(c, geoId, 1), e = involvesGeoIdAndPosId(c, geoId, 2);
		const keepStart = cutting[0] !== GEO_UNDEF, keepEnd = cutting[1] !== GEO_UNDEF;
		return !(!(s && e && !(keepStart && keepEnd)) && (s && keepStart || e && keepEnd));
	});
	oldIds = oldIds.filter((i) => !involvesGeoIdAndPosId(d.constraints[i], geoId, 3));
	const newCons = [], toDelete = /* @__PURE__ */ new Set();
	let point1Done = false, point2Done = false;
	const conic = hasMid(geo);
	for (const id of oldIds) {
		const con = d.constraints[id];
		if (con.type === "InternalAlignment") {
			if (conic) newCons.push({
				...clone(con),
				second: newIds[0]
			});
			else toDelete.add(con.first);
			continue;
		}
		let n = transformPreexistingForTrim(d, con, geoId, cutting[0], cuts[0], newIds[0], 2);
		if (n) {
			newCons.push(n);
			point1Done = true;
			continue;
		}
		n = transformPreexistingForTrim(d, con, geoId, cutting[1], cuts[1], newIds[newIds.length - 1], 1);
		if (n) {
			newCons.push(n);
			point2Done = true;
			continue;
		}
		if (!(con.type === "Angle" || involvesGeoIdAndPosId(con, geoId, 0))) continue;
		deriveConstraintsForPieces(d, geoId, newIds, newGeos, con, newCons, false);
	}
	if (cutting[0] !== -2e3 && !point1Done) newCons.push(newConstraintAtTrimCut(d, cutting[0], newIds[0], 2, cuts[0]));
	if (cutting[1] !== -2e3 && !point2Done) newCons.push(newConstraintAtTrimCut(d, cutting[1], newIds[newIds.length - 1], 1, cuts[1]));
	delConstraints(d, oldIds);
	if (!closed) {
		transferConstraints(d, geoId, 1, newIds[0], 1, true);
		transferConstraints(d, geoId, 2, newIds[newIds.length - 1], 2, true);
	}
	if (conic) {
		transferConstraints(d, geoId, 3, newIds[0], 3, true);
		if (newIds.length > 1) newCons.push(constraint("Coincident", newIds[0], 3, newIds[newIds.length - 1], 3));
	}
	d.geometry = [...d.geometry];
	d.geometry[geoId] = newGeos[0];
	for (let i = 1; i < newGeos.length; i++) d.geometry.push(newGeos[i]);
	for (const id of newIds) d.geometry[id] = construction ? {
		...d.geometry[id],
		construction: true
	} : withoutConstruction(d.geometry[id]);
	let added = newCons;
	for (const g of [...toDelete].sort((a, b) => b - a)) added = added.map((c) => afterDeletingGeo(c, g)).filter((c) => !!c);
	delGeometries(d, [...toDelete]);
	d.constraints = [...d.constraints, ...added];
	return true;
}
function withoutConstruction(g) {
	const { construction: _c, ...rest } = g;
	return rest;
}
function split(d, geoId, point, k) {
	return withOpKernel(k ?? kernel ?? void 0, () => splitIt(d, geoId, point));
}
function splitIt(d, geoId, point) {
	const geo = d.geometry[geoId];
	if (!geo || geo.type === "Point") return false;
	const closed = isClosedCurve(geo);
	const u = closestParam(geo, point);
	const [first, last] = range(geo);
	const params = closed ? [[u, u + last - first]] : [[first, u], [u, last]];
	const newIds = params.length === 1 ? [geoId] : [geoId, d.geometry.length];
	const newGeos = params.map(([a, b]) => createArc(geo, a, b));
	let oldIds = constraintIndices(d, geoId);
	oldIds = oldIds.filter((i) => involvesGeoIdAndPosId(d.constraints[i], geoId, 0));
	const newCons = [];
	if (!closed && newIds.length > 1) {
		transferConstraints(d, geoId, 1, newIds[0], 1, true);
		transferConstraints(d, geoId, 2, newIds[newIds.length - 1], 2, true);
	}
	for (const id of oldIds) deriveConstraintsForPieces(d, geoId, newIds, newGeos, d.constraints[id], newCons, true);
	let joint = null;
	if (!closed && newIds.length > 1) {
		joint = constraint("Coincident", newIds[0], 2, newIds[newIds.length - 1], 1);
		newCons.push(joint);
	}
	if (hasMid(geo) && newIds.length > 1) newCons.push(constraint("Coincident", newIds[0], 3, newIds[newIds.length - 1], 3));
	else if (joint && (geo.type === "LineSegment" || geo.type === "BSplineCurve")) joint.type = "Tangent";
	if (hasMid(geo)) transferConstraints(d, geoId, 3, newIds[0], 3);
	delConstraints(d, oldIds);
	d.geometry = [...d.geometry];
	d.geometry[geoId] = newGeos[0];
	for (let i = 1; i < newGeos.length; i++) d.geometry.push(newGeos[i]);
	d.constraints = [...d.constraints, ...newCons];
	return true;
}
/** find2DLinesIntersection. */
function linesIntersection(o1, d1, o2, d2) {
	const det = d1[0] * d2[1] - d1[1] * d2[0];
	if (Math.abs(det) < 1e-10) return null;
	const c1 = d1[1] * o1[0] - d1[0] * o1[1], c2 = d2[1] * o2[0] - d2[0] * o2[1];
	return [(d1[0] * c2 - d2[0] * c1) / det, (d1[1] * c2 - d2[1] * c1) / det];
}
const segIntersection = (l1, l2) => linesIntersection(l1.start, sub(l1.end, l1.start), l2.start, sub(l2.end, l2.start));
/** findFilletCenter. */
function filletCenter(l1, l2, radius, ref1, ref2) {
	const dir1 = normalize(sub(l1.start, l1.end)), dir2 = normalize(sub(l2.start, l2.end));
	let n1 = normalize([dir1[1], -dir1[0]]), n2 = normalize([dir2[1], -dir2[0]]);
	const corner = segIntersection(l1, l2);
	if (!corner) return null;
	const np1 = add(projectToLine(sub(ref1, l1.start), sub(l1.end, l1.start)), ref1);
	const np2 = add(projectToLine(sub(ref2, l2.start), sub(l2.end, l2.start)), ref2);
	const bisect = normalize(add(normalize(sub(np1, corner)), normalize(sub(np2, corner))));
	const i1 = linesIntersection(np1, n1, corner, bisect), i2 = linesIntersection(np2, n2, corner, bisect);
	if (!i1 || !i2) return null;
	n1 = normalize(sub(i1, np1));
	n2 = normalize(sub(i2, np2));
	return linesIntersection(add(l1.start, mul(n1, radius)), dir1, add(l2.start, mul(n2, radius)), dir2);
}
/** create2LinesFilletGeometry. */
function lineFilletArc(l1, l2, center, radius) {
	const corner = segIntersection(l1, l2);
	if (!corner) return null;
	const d1 = sub(l1.end, l1.start), d2 = sub(l2.end, l2.start);
	const r1 = mul(projectToLine(sub(center, corner), d1), 1), r2 = projectToLine(sub(center, corner), d2);
	let start = Math.atan2(r1[1], r1[0]);
	const span = Math.atan2(-r1[1] * r2[0] + r1[0] * r2[1], r1[0] * r2[0] + r1[1] * r2[1]);
	let end = start + span;
	if (end < start) [start, end] = [end, start];
	if (end > TWO_PI$1) end -= TWO_PI$1;
	if (start < 0) end += TWO_PI$1;
	const [a, b] = setTrimPeriodic(start, end);
	return {
		type: "ArcOfCircle",
		center,
		radius,
		start_angle: a,
		end_angle: b
	};
}
/** createFilletGeometry for two lines. */
function lineFillet(l1, l2, ref1, ref2, radius) {
	const center = filletCenter(l1, l2, radius, ref1, ref2);
	if (!center) return null;
	const arc = lineFilletArc(l1, l2, center, radius);
	if (!arc) return null;
	const corner = segIntersection(l1, l2);
	const p1a = valueAt(arc, arc.start_angle);
	const dir1 = sub(l1.end, l1.start), dir2 = sub(l2.end, l2.start);
	const dist1 = projectToLine(sub(p1a, corner), dir1), dist2 = projectToLine(sub(p1a, corner), dir2);
	return {
		arc,
		pos1: dot(sub(center, corner), dir1) > 0 ? 1 : 2,
		pos2: dot(sub(center, corner), dir2) > 0 ? 1 : 2,
		reverse: len(dist1) < len(dist2)
	};
}
/** SketchObject::fillet(GeoId1, GeoId2, refPnt1, refPnt2, radius, trim, createCorner, chamfer): two lines here, two
*  other bounded curves through the kernel (createFilletGeometry's offset curves, OCCT's extrema). */
function fillet(d, geoId1, geoId2, ref1, ref2, radius, trimIt, createCorner, chamfer, move, k) {
	return withOpKernel(k, () => filletIt(d, geoId1, geoId2, ref1, ref2, radius, trimIt, createCorner, chamfer, move));
}
const BOUNDED = [
	"LineSegment",
	"ArcOfCircle",
	"ArcOfEllipse",
	"ArcOfHyperbola",
	"ArcOfParabola",
	"BSplineCurve"
];
function filletIt(d, geoId1, geoId2, ref1, ref2, radius, trimIt, createCorner, chamfer, move) {
	if (!d.geometry[geoId1] || !d.geometry[geoId2]) return false;
	if (!d.constraints.some((c) => c.type === "Coincident" && involvesGeoId(c, geoId1) && involvesGeoId(c, geoId2))) return false;
	const l1 = d.geometry[geoId1], l2 = d.geometry[geoId2];
	let made;
	if (l1.type === "LineSegment" && l2.type === "LineSegment") made = lineFillet(l1, l2, ref1, ref2, radius);
	else if (BOUNDED.includes(l1.type) && BOUNDED.includes(l2.type)) {
		const r = needKernel("A fillet between curves other than two lines")({
			op: "fillet",
			geo1: plainGeo(l1),
			geo2: plainGeo(l2),
			ref1,
			ref2,
			radius
		}).fillet;
		made = r && {
			arc: r.arc,
			pos1: r.pos1,
			pos2: r.pos2,
			reverse: r.reverse
		};
	} else made = null;
	if (!made) return false;
	const { arc, pos1, pos2, reverse } = made;
	const filletId = d.geometry.length;
	d.geometry = [...d.geometry, arc];
	let p1 = valueAt(arc, arc.start_angle), p2 = valueAt(arc, arc.end_angle);
	if (!reverse) [p1, p2] = [p2, p1];
	let filletPos1 = 0, filletPos2 = 0;
	let g1 = geoId1, g2 = geoId2;
	if (trimIt) {
		let newId1 = -1, newId2 = -1, swapped1 = false, swapped2 = false;
		if (createCorner) {
			if (!(!!coincidentPoints(d.constraints, g1, pos1).get(g2) && coincidentPoints(d.constraints, g1, pos1).get(g2) === pos2)) {
				delConstraintOnPoint(d, g1, pos1, false);
				delConstraintOnPoint(d, g2, pos2, false);
				delConstraints(d, d.constraints.map((c, i) => (c.type === "Distance" || c.type === "Equal") && (c.first === g1 && c.firstPos === 0 || c.first === g2 && c.firstPos === 0) ? i : -1).filter((i) => i >= 0));
			} else {
				const splitCorner = (geoId, pos, p) => {
					const highest = d.geometry.length - 1;
					split(d, geoId, p);
					let newId = highest + 1, id = geoId;
					const needsSwap = pos === 1;
					if (needsSwap) [newId, id] = [id, newId];
					d.geometry = d.geometry.map((x, i) => i === newId ? {
						...x,
						construction: true
					} : x);
					return [
						id,
						newId,
						needsSwap
					];
				};
				[g1, newId1, swapped1] = splitCorner(g1, pos1, p1);
				[g2, newId2, swapped2] = splitCorner(g2, pos2, p2);
			}
		} else {
			delConstraintOnPoint(d, g1, pos1, false);
			delConstraintOnPoint(d, g2, pos2, false);
		}
		filletPos1 = reverse ? 1 : 2;
		filletPos2 = reverse ? 2 : 1;
		for (const [g, pos, p] of [[
			g1,
			pos1,
			p1
		], [
			g2,
			pos2,
			p2
		]]) {
			const out = move(d, g, pos, p);
			if (out) d.geometry = out;
		}
		d.constraints = [
			...d.constraints,
			constraint("Tangent", g1, pos1, filletId, filletPos1),
			constraint("Tangent", g2, pos2, filletId, filletPos2)
		];
		if (createCorner) {
			const swap = (geoId, newId, swapped) => {
				if (swapped || newId < 0) return;
				const temp = d.geometry.length;
				d.constraints = d.constraints.map((c) => {
					const n = clone(c);
					substituteIndex(n, geoId, temp);
					substituteIndex(n, newId, geoId);
					substituteIndex(n, temp, newId);
					return n;
				});
				const gs = [...d.geometry];
				[gs[geoId], gs[newId]] = [gs[newId], gs[geoId]];
				d.geometry = gs;
			};
			swap(g1, newId1, swapped1);
			swap(g2, newId2, swapped2);
		}
	}
	if (chamfer) {
		const lineId = d.geometry.length;
		d.geometry = [...d.geometry, {
			type: "LineSegment",
			start: p1,
			end: p2
		}];
		d.constraints = [
			...d.constraints,
			trimIt ? constraint("Coincident", lineId, filletPos1, g1, pos1) : constraint("Coincident", lineId, filletPos1, filletId, 1),
			trimIt ? constraint("Coincident", lineId, filletPos2, g2, pos2) : constraint("Coincident", lineId, filletPos2, filletId, 2)
		];
		d.geometry = d.geometry.map((x, i) => i === filletId ? {
			...x,
			construction: true
		} : x);
	}
	return true;
}
//#endregion
//#region ui/src/sketchbspline.ts
/** The geometry as the kernel takes it: the curve alone (no construction flag, no cached end points). */
function plain(g) {
	const { construction: _c, start_point: _s, end_point: _e, ...rest } = g;
	return rest;
}
const withConstruction = (g, c) => c ? {
	...plain(g),
	construction: true
} : plain(g);
const isBSpline = (g) => g?.type === "BSplineCurve";
/** SketchObject::getHighestCurveIndex. */
const highest = (d) => d.geometry.length - 1;
/** SketchObject::exposeInternalGeometry(GeoId) on a sketch: the internal geometry the constraints do not already give
*  the conic or B-spline, as construction geometry, then its InternalAlignment (a B-spline's Weight and Equal too)
*  constraints. The number of elements added, -1 for a curve that has none. */
function exposeInternalGeometry(d, geoId) {
	const refs = d.constraints.filter((c) => c.type === "InternalAlignment" && c.alignment).map((c) => ({
		first: c.first,
		second: c.second,
		alignment: c.alignment,
		index: c.alignmentIndex ?? -1
	}));
	const weighted = (circle) => d.constraints.some((c) => c.type === "Weight" && c.first === circle);
	const ex = exposeInternalGeometry$1(d.geometry, refs, geoId, weighted);
	if (!ex) return -1;
	d.geometry = [...d.geometry, ...ex.geometry];
	const list = ex.order.map((k) => {
		if (k >= 0) {
			const a = ex.alignments[k];
			return alignmentConstraint(a.alignment, a.first, a.firstPos, a.second, a.index);
		}
		const o = ex.others[-1 - k];
		return o.type === "Weight" ? constraint("Weight", o.first, 0, GEO_UNDEF, 0, GEO_UNDEF, 0, o.value ?? 1) : constraint("Equal", o.first, 0, o.second);
	});
	d.constraints = [...d.constraints, ...list];
	return ex.geometry.length;
}
/** SketchObject::replaceGeometries(oldGeoIds, newGeos): the new curves in place of the old ones, the extra new ones at
*  the end, the extra old ones deleted (with their internal geometry). */
function replaceGeometries(d, oldIds, newGeos) {
	d.geometry = [...d.geometry];
	let i = 0;
	for (; i < oldIds.length && i < newGeos.length; i++) d.geometry[oldIds[i]] = newGeos[i];
	for (let j = i; j < newGeos.length; j++) d.geometry.push(newGeos[j]);
	if (i < oldIds.length) delGeometries(d, oldIds.slice(i));
}
/** SketchObject::convertToNURBS(GeoId): the curve replaced by its B-spline (a new geometry: not construction), its
*  constraints other than coincidences gone, and the coincidences on its centre. */
function convertToNURBS(d, geoId, k, external) {
	if (geoId > highest(d) || geoId === -1 || geoId === -2) return false;
	if (geoId < 0) {
		const ext = external?.(geoId);
		if (!ext || ext.type === "Point") return false;
		d.geometry = [...d.geometry, k({
			op: "nurbs",
			geo: plain(ext)
		}).geo];
		return true;
	}
	const geo = d.geometry[geoId];
	if (!geo || geo.type === "Point") return false;
	const bsp = k({
		op: "nurbs",
		geo: plain(geo)
	}).geo;
	d.geometry = [...d.geometry];
	d.geometry[geoId] = bsp;
	d.constraints = d.constraints.filter((c) => !(c.type !== "Coincident" && involvesGeoId(c, geoId) || c.type === "Coincident" && involvesGeoIdAndPosId(c, geoId, 3)));
	return true;
}
/** SketchObject::increaseBSplineDegree(GeoId, degreeincrement). */
function increaseBSplineDegree(d, geoId, k, increment = 1) {
	if (geoId < 0 || geoId > highest(d)) return false;
	const geo = d.geometry[geoId];
	if (!isBSpline(geo)) return false;
	const a = k({
		op: "degree",
		geo: plain(geo),
		degree: geo.degree + increment
	});
	d.geometry = [...d.geometry];
	d.geometry[geoId] = a.geo;
	return true;
}
/** SketchObject::decreaseBSplineDegree(GeoId, degreedecrement): the B-spline approximated at the lower degree (OCCT's
*  Approx_Curve3d), the old one deleted with its internal geometry and the new one added at the end with its own. The
*  new curve's GeoId, or -1. */
function decreaseBSplineDegree(d, geoId, k, decrement = 1) {
	if (geoId < 0 || geoId > highest(d)) return -1;
	const geo = d.geometry[geoId];
	if (!isBSpline(geo)) return -1;
	const max = geo.degree - decrement;
	if (max === 0) return -1;
	const a = k({
		op: "approximate",
		geo: plain(geo),
		degree: max
	});
	delGeometry(d, geoId, true);
	d.geometry = [...d.geometry, a.geo];
	const newId = d.geometry.length - 1;
	exposeInternalGeometry(d, newId);
	return newId;
}
/** What FreeCAD throws (Base::ValueError, TypeError, CADKernelError): the message the command reports. */
var SketchError = class extends Error {};
const sameXY = (a, b) => Math.abs(a[0] - b[0]) <= Number.EPSILON && Math.abs(a[1] - b[1]) <= Number.EPSILON;
/** The pole and knot constraints of the B-spline geoId moved to the new B-spline's indices (std::ranges::find of the
*  old pole, Base::Vector3d's ==, and of the old knot, exact), the internal geometry of the ones it no longer has
*  deleted; the B-spline's GeoId after it. */
function reindexInternal(d, geoId, old, neu) {
	const poleIn = old.poles.map((p) => {
		return neu.poles.findIndex((q) => sameXY(p, q));
	});
	const knotIn = old.knots.map((u) => neu.knots.indexOf(u));
	const del = [];
	const cons = [];
	for (const c of d.constraints) {
		if (!(c.type === "InternalAlignment" && c.second === geoId)) {
			cons.push(c);
			continue;
		}
		const map = c.alignment === "BSplineControlPoint" ? poleIn : c.alignment === "BSplineKnotPoint" ? knotIn : null;
		if (!map) {
			cons.push(c);
			continue;
		}
		const index = map[c.alignmentIndex ?? -1] ?? -1;
		if (index === -1) {
			del.push(c.first);
			continue;
		}
		cons.push({
			...c,
			alignmentIndex: index
		});
	}
	d.geometry = [...d.geometry];
	d.geometry[geoId] = withConstruction(neu, !!old.construction);
	d.constraints = cons;
	if (del.length) delGeometriesExclusive(d, del);
	return geoId - [...new Set(del)].filter((g) => g < geoId).length;
}
/** SketchObject::modifyBSplineKnotMultiplicity(GeoId, knotIndex (OCC's, from 1), multiplicityincr); throws
*  SketchError with FreeCAD's message. The B-spline's GeoId after it. */
function modifyBSplineKnotMultiplicity(d, geoId, knotIndex, incr, k) {
	if (geoId < 0 || geoId > highest(d)) throw new SketchError("B-spline Geometry Index (GeoID) is out of bounds.");
	if (incr === 0) throw new SketchError("You are requesting no change in knot multiplicity.");
	const geo = d.geometry[geoId];
	if (!isBSpline(geo)) throw new SketchError("The Geometry Index (GeoId) provided is not a B-spline.");
	if (knotIndex > geo.knots.length || knotIndex < 1) throw new SketchError("The knot index is out of bounds. Note that in accordance with OCC notation, the first knot has index 1 and not zero.");
	const cur = geo.mults[knotIndex - 1];
	if (cur + incr > geo.degree) throw new SketchError("The multiplicity cannot be increased beyond the degree of the B-spline.");
	if (cur + incr < 0) throw new SketchError("The multiplicity cannot be decreased beyond zero.");
	return reindexInternal(d, geoId, geo, k({
		op: "multiplicity",
		geo: plain(geo),
		index: knotIndex,
		mult: cur + incr
	}).geo);
}
/** SketchObject::insertBSplineKnot(GeoId, param, multiplicity); throws SketchError. The B-spline's GeoId after it. */
function insertBSplineKnot(d, geoId, param, mult, k) {
	if (geoId < 0 || geoId > highest(d)) throw new SketchError("B-spline Geometry Index (GeoID) is out of bounds.");
	if (mult === 0) throw new SketchError("Knot cannot have zero multiplicity.");
	const geo = d.geometry[geoId];
	if (!isBSpline(geo)) throw new SketchError("The Geometry Index (GeoId) provided is not a B-spline.");
	const [first, last] = bsplineRange(geo);
	if (mult > geo.degree) throw new SketchError("Knot multiplicity cannot be higher than the degree of the B-spline.");
	if (param > last || param < first) throw new SketchError("Knot cannot be inserted outside the B-spline parameter range.");
	return reindexInternal(d, geoId, geo, k({
		op: "insert_knot",
		geo: plain(geo),
		u: param,
		mult
	}).geo);
}
/** SketchObject::join(geoId1, posId1, geoId2, posId2, continuity): the two curves made one B-spline in geoId1's place;
*  throws SketchError with FreeCAD's message. */
function join(d, g1, p1, g2, p2, continuity, k) {
	if (p1 !== 1 && p1 !== 2 && p2 !== 1 && p2 !== 2) throw new SketchError("Invalid positions: points must be start or end points of a curve.");
	if (g1 === g2) throw new SketchError("Connecting the end points of the same curve is not yet supported.");
	if (g1 < 0 || g1 > highest(d) || g2 < 0 || g2 > highest(d)) return false;
	const geo1 = d.geometry[g1], geo2 = d.geometry[g2];
	if (geo1.type === "Point" || geo2.type === "Point") return false;
	const c1 = !!geo1.construction;
	if (c1 !== !!geo2.construction) throw new SketchError("Cannot join construction and non-construction geometries.");
	const a = k({
		op: "join",
		geo1: plain(geo1),
		pos1: p1,
		geo2: plain(geo2),
		pos2: p2,
		continuity
	});
	replaceGeometries(d, [g1, g2], [a.geo]);
	exposeInternalGeometry(d, g1);
	d.geometry[g1] = withConstruction(d.geometry[g1], c1);
	const other1 = p1 === 1 ? 2 : 1, other2 = p2 === 1 ? 2 : 1;
	transferConstraints(d, g1, other1, g1, 1, true);
	transferConstraints(d, g2, other2, g1, 2, true);
	return true;
}
/** The knot points of the tool: Part.Point construction geometry, one per click (the handler's addGeometry). */
function knotPoint(p) {
	return {
		type: "Point",
		at: [Number(p[0].toFixed(6)), Number(p[1].toFixed(6))],
		construction: true
	};
}
/** C++'s default stream output of a double (6 significant digits), as the handler writes App.Vector(x, y). */
const g6 = (v) => Number(v.toPrecision(6));
/** The B-spline the handler makes through points (the knot points at firstPointId...): the curve interpolated in pieces
*  between C0 knots (multiplicity >= 3), raised to degree 3, added after the points; the ends' autoconstraints moved to
*  the curve's ends, each point tied to the curve (InternalAlignment BSplineKnotPoint, or PointOnObject between two
*  C0 knots), the knot multiplicities asked for set, then exposeInternalGeometry. The new curve's GeoId. */
function bsplineByKnots(d, firstPointId, points, multiplicities, periodic, construction, k) {
	const degree = 3;
	const mults = [...multiplicities];
	if (!periodic) {
		mults[0] = 4;
		mults[mults.length - 1] = 4;
	}
	const pts = points.map((p) => [g6(p[0]), g6(p[1])]);
	const pieces = [[pts[0]]];
	for (let i = 1; i < pts.length - 1; i++) {
		pieces[pieces.length - 1].push(pts[i]);
		if (mults[i] >= degree) pieces.push([pts[i]]);
	}
	pieces[pieces.length - 1].push(pts[pts.length - 1]);
	const between = pts.map((_, i) => i > 0 && i < pts.length - 1 && mults[i - 1] >= degree && mults[i + 1] >= degree);
	let poles = [], knots = [], ms = [];
	pieces.forEach((piece, n) => {
		const b = k({
			op: "interpolate",
			points: piece,
			periodic,
			degree
		}).geo;
		if (n === 0) {
			poles = [...b.poles];
			knots = [...b.knots];
			ms = [...b.mults];
		} else {
			poles.push(...b.poles.slice(1));
			const last = knots[knots.length - 1];
			knots.push(...b.knots.slice(1).map((u) => last + u));
			ms[ms.length - 1] = 3;
			ms.push(...b.mults.slice(1));
		}
	});
	const bsp = {
		type: "BSplineCurve",
		poles,
		weights: poles.map(() => 1),
		knots,
		mults: ms,
		degree,
		periodic,
		...construction ? { construction: true } : {}
	};
	d.geometry = [...d.geometry, bsp];
	let id = d.geometry.length - 1;
	if (!periodic) {
		const ids = points.map((_, i) => firstPointId + i);
		d.constraints = d.constraints.map((c) => {
			if (c.first === ids[0] && c.firstPos === 1) return {
				...c,
				first: id,
				firstPos: 1
			};
			if (c.first === ids[ids.length - 1] && c.firstPos === 1) return {
				...c,
				first: id,
				firstPos: 2
			};
			return c;
		});
	}
	const list = [];
	let knot = 0;
	for (let i = 0; i < points.length; i++) {
		if (between[i]) {
			list.push(constraint("PointOnObject", firstPointId + i, 1, id));
			continue;
		}
		list.push(alignmentConstraint("BSplineKnotPoint", firstPointId + i, 1, id, knot));
		if (mults[i] > 1 && mults[i] < degree) id = modifyBSplineKnotMultiplicity(d, id, knot + 1, mults[i] - 1, k);
		knot++;
	}
	d.constraints = [...d.constraints, ...list];
	exposeInternalGeometry(d, id);
	return id;
}
//#endregion
//#region ui/src/sketchkernel.ts
/** A function's request for answers it has not got: withKernel catches it. */
var KernelNeeded = class extends Error {
	reqs;
	constructor(reqs) {
		super("kernel answers needed");
		this.reqs = reqs;
	}
};
/** What the server refused (OCCT's or FreeCAD's message). */
var KernelError = class extends Error {};
const keyOf = (r) => JSON.stringify(r);
/** The answer to req from the cache; throws KernelNeeded when it is not there, KernelError when it was refused. */
function cached(cache) {
	return (req) => {
		const a = cache.get(keyOf(req));
		if (!a) throw new KernelNeeded([req]);
		if (a.error !== void 0) throw new KernelError(a.error);
		return a;
	};
}
//#endregion
//#region ui/src/sketchcarbon.ts
const CONFUSION = 1e-7;
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub3 = (a, b) => [
	a[0] - b[0],
	a[1] - b[1],
	a[2] - b[2]
];
/** Base::Rotation::multVec (the quaternion x, y, z, w). */
function multVec(q, v) {
	const [x, y, z, w] = q;
	const x2 = x * x, y2 = y * y, z2 = z * z, w2 = w * w;
	return [
		(x2 + w2 - y2 - z2) * v[0] + 2 * (x * y - z * w) * v[1] + 2 * (x * z + y * w) * v[2],
		2 * (x * y + z * w) * v[0] + (w2 - x2 + y2 - z2) * v[1] + 2 * (y * z - x * w) * v[2],
		2 * (x * z - y * w) * v[0] + 2 * (x * w + y * z) * v[1] + (w2 - x2 - y2 + z2) * v[2]
	];
}
const normalize3 = (v) => {
	const l = Math.hypot(...v);
	return l ? [
		v[0] / l,
		v[1] / l,
		v[2] / l
	] : v;
};
/** isCarbonCopyAllowed's placement checks (the sketch of the source, `src`, onto this one): the planes parallel, the
*  axes aligned, the origins on one normal; xinv / yinv when the X / Y axes run opposite. */
function carbonCopyAllowed(self, src, allowUnaligned = false) {
	const sn = multVec(src.rotation, [
		0,
		0,
		1
	]), sx = multVec(src.rotation, [
		1,
		0,
		0
	]), sy = multVec(src.rotation, [
		0,
		1,
		0
	]);
	const ln = multVec(self.rotation, [
		0,
		0,
		1
	]), lx = multVec(self.rotation, [
		1,
		0,
		0
	]), ly = multVec(self.rotation, [
		0,
		1,
		0
	]);
	const d = dot3(sn, ln), dx = dot3(sx, lx), dy = dot3(sy, ly);
	if (!allowUnaligned && Math.abs(Math.abs(d) - 1) > CONFUSION) return { reason: "rlNonParallel" };
	if (!allowUnaligned && (Math.abs(Math.abs(dx) - 1) > CONFUSION || Math.abs(Math.abs(dy) - 1) > CONFUSION)) return { reason: "rlAxesMisaligned" };
	const same = src.base[0] === self.base[0] && src.base[1] === self.base[1] && src.base[2] === self.base[2];
	const ddir = normalize3(sub3(src.base, self.base));
	if (!allowUnaligned && Math.abs(Math.abs(dot3(ddir, ln)) - 1) > CONFUSION && !same) return { reason: "rlOriginsMisaligned" };
	return {
		xinv: allowUnaligned ? false : Math.abs(dx - 1) > CONFUSION,
		yinv: allowUnaligned ? false : Math.abs(dy - 1) > CONFUSION
	};
}
/** gp_Pnt::Mirror(gp_Ax1): the point turned half a turn about the axis through o along d; the sketch keeps x and y. */
function mirrorPoint(p, o, d) {
	const v = [
		p[0] - o[0],
		p[1] - o[1],
		-o[2]
	];
	const t = dot3(v, d);
	return [2 * (o[0] + d[0] * t) - p[0], 2 * (o[1] + d[1] * t) - p[1]];
}
/** gp_Dir::Mirror(gp_Ax1) of a direction in the plane. */
function mirrorDir(v, d) {
	const t = v[0] * d[0] + v[1] * d[1];
	return [2 * d[0] * t - v[0], 2 * d[1] * t - v[1]];
}
const TWO_PI = 2 * Math.PI;
const norm0 = (a) => a - Math.floor(a / TWO_PI) * TWO_PI;
/** A sketch curve turned half a turn about an axis (Part::Geometry::mirror(point, dir), the axis in global terms as
*  carbonCopy gives it): about an axis in the plane it is mirrored, its normal goes to -Z and the Sketcher reads an arc
*  counter-clockwise from its other end; about an axis along the normal it is only turned in the plane. */
function mirrorGeo(g, o, d) {
	const P = (p) => mirrorPoint(p, o, d);
	const reversed = 2 * d[2] * d[2] - 1 < 0;
	switch (g.type) {
		case "Point": return {
			...g,
			at: P(g.at)
		};
		case "LineSegment": return {
			...g,
			start: P(g.start),
			end: P(g.end)
		};
		case "Circle": return {
			...g,
			center: P(g.center)
		};
		case "ArcOfCircle": {
			const ang = reversed ? g.end_angle : g.start_angle;
			const c = P(g.center), e = P([g.center[0] + g.radius * Math.cos(ang), g.center[1] + g.radius * Math.sin(ang)]);
			const a1 = norm0(Math.atan2(e[1] - c[1], e[0] - c[0]));
			return {
				...g,
				center: c,
				start_angle: a1,
				end_angle: a1 + (g.end_angle - g.start_angle)
			};
		}
		case "Ellipse": return {
			...g,
			center: P(g.center),
			x_axis: mirrorDir(g.x_axis, d)
		};
		case "ArcOfEllipse":
		case "ArcOfHyperbola":
		case "ArcOfParabola": {
			const { start_point: _s, end_point: _e, ...rest } = g;
			const [u1, u2] = reversed ? [-g.end_angle, -g.start_angle] : [g.start_angle, g.end_angle];
			return {
				...rest,
				center: P(g.center),
				x_axis: mirrorDir(g.x_axis, d),
				start_angle: u1,
				end_angle: u2
			};
		}
		case "BSplineCurve": return {
			...g,
			poles: g.poles.map(P)
		};
	}
}
/** The constraint corrections for flipped geometry (applyConstraintFlipCorrection). */
function flipConstraint(c, xinv, yinv) {
	if (!xinv && !yinv) return c;
	const n = { ...c };
	if (xinv && n.type === "DistanceX" || yinv && n.type === "DistanceY") {
		if (n.first === n.second) [n.firstPos, n.secondPos] = [n.secondPos, n.firstPos];
		else n.value = -n.value;
	}
	if (n.type === "Angle") {
		const na = (a) => {
			while (a > Math.PI) a -= Math.PI * 2;
			while (a <= -Math.PI) a += Math.PI * 2;
			return a;
		};
		if (xinv && yinv) {
			if (n.first === -1 || n.second === -1 || n.first === -2 || n.second === -2 || n.second === -2e3) n.value = na(n.value + Math.PI);
		} else if (xinv) {
			if (n.first === -1 || n.second === -1 || n.second === -2e3) n.value = na(Math.PI - n.value);
			else n.value = na(-n.value);
		} else if (yinv) {
			if (n.first === -2 || n.second === -2) n.value = na(Math.PI - n.value);
			else n.value = na(-n.value);
		}
	}
	return n;
}
/** SketchObject::carbonCopy's geometry and constraints: src's geometry after this sketch's (mirrored for xinv / yinv about
*  this sketch's own axes through its origin, as FreeCAD gives Part::Geometry::mirror this Placement's position and
*  axes), construction when asked (but points), src's constraints with their GeoIds moved (its own past ours, its
*  external ones past our externalCount, axes included as getExternalGeometryCount counts them). */
function carbonCopy(d, src, self, xinv, yinv, construction, externalCount) {
	const next = d.geometry.length;
	const o = self.base, axisH = multVec(self.rotation, [
		1,
		0,
		0
	]), axisV = multVec(self.rotation, [
		0,
		1,
		0
	]);
	const geos = src.geometry.map((g0) => {
		let g = { ...g0 };
		if (xinv) g = mirrorGeo(g, o, axisV);
		if (yinv) g = mirrorGeo(g, o, axisH);
		if (construction && g.type !== "Point") g = {
			...g,
			construction: true
		};
		return g;
	});
	const cons = src.constraints.map((c0) => {
		const c = { ...c0 };
		for (const k of [
			"first",
			"second",
			"third"
		]) if (c0[k] >= 0) c[k] = c0[k] + next;
		else if (c0[k] < -2 && c0[k] !== -2e3) c[k] = c0[k] - (externalCount - 2);
		return flipConstraint(c, xinv, yinv);
	});
	d.geometry = [...d.geometry, ...geos];
	d.constraints = [...d.constraints, ...cons];
	return src.geometry.length;
}
//#endregion
//#region ui/scripts/sketchcurves-entry.ts
const DIMENSIONAL = [
	"Distance",
	"DistanceX",
	"DistanceY",
	"Radius",
	"Diameter",
	"Angle",
	"Weight"
];
function toConstraint(a) {
	const type = a[0], rest = a.slice(1);
	if (DIMENSIONAL.includes(type)) return fromCons({
		type,
		args: rest.slice(0, -1),
		value: rest[rest.length - 1]
	});
	return fromCons({
		type,
		args: rest
	});
}
function out(c) {
	const d = {
		type: c.type,
		elements: [
			c.first,
			c.firstPos,
			c.second,
			c.secondPos,
			c.third,
			c.thirdPos
		]
	};
	if (c.type === "InternalAlignment") {
		d.alignment = c.alignment ?? "Undef";
		d.index = c.alignmentIndex ?? -1;
	}
	if (DIMENSIONAL.includes(c.type)) d.value = c.value;
	return d;
}
/** One case with the kernel answers in `answers` (by request): its result, or the requests it still needs. */
function runCase(c, solve, answers) {
	const doc = {
		geometry: c.geometry.map((g) => ({ ...g })),
		constraints: c.constraints.map(toConstraint)
	};
	const k = cached(answers);
	const move = (d, geo, pos, to) => {
		const r = solve(JSON.stringify({
			geometry: d.geometry,
			constraints: d.constraints.map(toCons),
			solve: false,
			drags: [{
				geo,
				pos,
				to,
				update_geometry: true
			}]
		}));
		return r.status_code === 0 ? r.stored_geometry : null;
	};
	for (const g of c.expose ?? []) exposeInternalGeometry(doc, g);
	const [op, args] = c.op;
	let ok = true;
	try {
		let done = true;
		if (op === "convert") {
			const ids = args[0];
			for (const g of ids) if (!convertToNURBS(doc, g, k)) done = false;
			if (done) for (const g of ids) exposeInternalGeometry(doc, g);
		} else if (op === "degree_up") {
			const [g] = args;
			done = increaseBSplineDegree(doc, g, k);
			if (done) exposeInternalGeometry(doc, g);
		} else if (op === "degree_down") decreaseBSplineDegree(doc, args[0], k);
		else if (op === "knot_mult") {
			const [g, i, inc] = args;
			exposeInternalGeometry(doc, modifyBSplineKnotMultiplicity(doc, g, i, inc, k));
		} else if (op === "insert_knot") {
			const [g, u, m] = args;
			exposeInternalGeometry(doc, insertBSplineKnot(doc, g, u, m, k));
		} else if (op === "join") {
			const [g1, p1, g2, p2, cont] = args;
			done = join(doc, g1, p1, g2, p2, cont, k);
		} else if (op === "trim") {
			const [g, p, axes] = args;
			done = trim(doc, g, p, axes, k);
		} else if (op === "split") {
			const [g, p] = args;
			done = split(doc, g, p, k);
		} else if (op === "fillet") {
			const [g1, g2, r1, r2, rad, trim, corner, chamfer] = args;
			done = fillet(doc, g1, g2, r1, r2, rad, trim, corner, chamfer, move, k);
		} else if (op === "bspline_by_knots") {
			const [pts, mults, periodic, construction] = args;
			const first = doc.geometry.length;
			doc.geometry = [...doc.geometry, ...pts.map(knotPoint)];
			bsplineByKnots(doc, first, pts, mults, periodic, construction, k);
		} else if (op === "carbon_copy") {
			const [geometry, constraints, selfPl, srcPl, construction] = args;
			const ok = carbonCopyAllowed(selfPl, srcPl);
			if ("reason" in ok) done = false;
			else {
				carbonCopy(doc, {
					geometry: geometry.map((g) => ({ ...g })),
					constraints: constraints.map(toConstraint)
				}, selfPl, ok.xinv, ok.yinv, construction, 2);
				const r = solve(JSON.stringify({
					geometry: doc.geometry,
					constraints: doc.constraints.map(toCons)
				}));
				if (r.status_code === 0) doc.geometry = r.stored_geometry;
			}
		} else throw new Error(`unknown op ${op}`);
		if (!done) ok = "refused";
	} catch (e) {
		if (e instanceof KernelNeeded) return { needs: e.reqs };
		ok = String(e);
	}
	return { result: {
		ok,
		geometry: doc.geometry.map((g) => {
			const { construction: _c, ...rest } = g;
			if (rest.type === "ArcOfCircle") {
				const a1 = rest.start_angle - Math.floor(rest.start_angle / (2 * Math.PI)) * 2 * Math.PI;
				return {
					...rest,
					start_angle: a1,
					end_angle: a1 + (rest.end_angle - rest.start_angle)
				};
			}
			return rest.type === "BSplineCurve" && !rest.weights ? {
				...rest,
				weights: rest.poles.map(() => 1)
			} : rest;
		}),
		constructions: doc.geometry.map((g) => !!g.construction),
		constraints: doc.constraints.map(out)
	} };
}
//#endregion
export { runCase };
