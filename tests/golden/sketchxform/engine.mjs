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
const len$1 = (a) => Math.hypot(a[0], a[1]);
const unit$1 = (a) => {
	const l = len$1(a);
	return l ? [a[0] / l, a[1] / l] : [1, 0];
};
/** The conic's X direction (Part's XAxis: the major axis, towards a parabola's focus) and Y = Z ^ X. */
function conicAxes(g) {
	const x = unit$1(g.x_axis ?? [1, 0]);
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
//#region ui/src/sketchxform.ts
const TWO_PI = 2 * Math.PI;
const CONFUSION = 1e-7;
const ANGULAR = 1e-12;
const PCONFUSION = CONFUSION * .01;
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const len = (a) => Math.hypot(a[0], a[1]);
const unit = (a) => {
	const l = len(a);
	return l ? [a[0] / l, a[1] / l] : [1, 0];
};
/** Base::fmod: the remainder, made positive. */
const fmod = (n, d) => {
	const m = n % d;
	return m >= 0 ? m : m + d;
};
/** Base::Vector3d::Perpendicular(base, dir): the foot of the perpendicular from p onto the line. */
const perpendicular = (p, base, dir) => {
	const t = dot(sub(p, base), dir) / dot(dir, dir);
	return add(base, mul(dir, t));
};
/** Geom_TrimmedCurve::SetTrim on a periodic curve (ElCLib::AdjustPeriodic). */
function setTrimPeriodic(u1, u2) {
	const preci = Math.min(Math.abs(u2 - u1) / 2, PCONFUSION);
	u1 -= Math.floor(u1 / TWO_PI) * TWO_PI;
	if (TWO_PI - u1 < preci) u1 -= TWO_PI;
	u2 -= Math.floor((u2 - u1) / TWO_PI) * TWO_PI;
	if (u2 - u1 < preci) u2 += TWO_PI;
	return [u1, u2];
}
/** GeomEllipse / GeomArcOfConic setMajorAxisDir and setXAxisDir: a zero vector keeps the old direction. */
const axisDir = (newdir, old) => dot(newdir, newdir) < CONFUSION * CONFUSION ? old : unit(newdir);
/** Geometry::copy for the arcs of conics: the cached end points go (the solver's JSON may carry them). */
function stripEnds(g) {
	const { start_point: _s, end_point: _e, ...rest } = g;
	return rest;
}
/** SketchObject::getGeometry: the axes are lines from the origin along X and Y; the external geometry is reachable at
*  its GeoIds when the array carries it (sketch.ts's withExternal). */
function geometryAt(d, g) {
	if (g === -1) return {
		type: "LineSegment",
		start: [0, 0],
		end: [1, 0]
	};
	if (g === -2) return {
		type: "LineSegment",
		start: [0, 0],
		end: [0, 1]
	};
	return d.geometry[g];
}
/** GeometryFacade::isInternalAligned: the geometry is the first element of an InternalAlignment. */
const isInternalAligned = (d, g) => d.constraints.some((c) => c.type === "InternalAlignment" && c.first === g);
/** The geometry an internal-aligned element defines (the second of its InternalAlignment), else GeoUndef. */
function definedGeometry(d, g) {
	const c = d.constraints.find((k) => k.type === "InternalAlignment" && k.first === g);
	return c ? c.second : GEO_UNDEF;
}
const pointOf = (d, g, pos) => getPoint(d.geometry, g, pos) ?? [0, 0];
/** SketchObject::getSymmetric: the mirror images of the geometry about the line refGeoId (refPosId none) or the point
*  (refGeoId, refPosId), the GeoId each gets (geoIdMap, from the next free one) and whether its start and end swap. */
function getSymmetric(d, geoIdList, refGeoId, refPosId = 0) {
	const out = [], geoIdMap = /* @__PURE__ */ new Map(), inverted = /* @__PURE__ */ new Map();
	let cgeoid = d.geometry.length;
	const shouldCopy = (g) => !isInternalAligned(d, g) || geoIdList.includes(definedGeometry(d, g));
	const done = (g, sym, inv) => {
		if (inv !== null && !inverted.has(g)) inverted.set(g, inv);
		out.push(sym);
		if (!geoIdMap.has(g)) geoIdMap.set(g, cgeoid);
		cgeoid++;
	};
	if (refPosId === 0) {
		const ref = geometryAt(d, refGeoId);
		if (ref?.type !== "LineSegment") return {
			geometry: [],
			geoIdMap,
			inverted
		};
		const base = ref.start, vectline = sub(ref.end, ref.start);
		const m = (p) => add(p, mul(sub(perpendicular(p, base, vectline), p), 2));
		for (const geoId of geoIdList) {
			const geo = geometryAt(d, geoId);
			if (!geo || !shouldCopy(geoId)) continue;
			switch (geo.type) {
				case "LineSegment":
					done(geoId, {
						...geo,
						start: m(geo.start),
						end: m(geo.end)
					}, false);
					break;
				case "Circle":
					done(geoId, {
						...geo,
						center: m(geo.center)
					}, false);
					break;
				case "ArcOfCircle": {
					const sp = pointOf(d, geoId, 1), ep = pointOf(d, geoId, 2);
					const ssp = m(sp), sep = m(ep), scp = m(geo.center);
					const [a, b] = setTrimPeriodic(fmod(Math.atan2(sep[1] - scp[1], sep[0] - scp[0]), TWO_PI), fmod(Math.atan2(ssp[1] - scp[1], ssp[0] - scp[0]), TWO_PI));
					done(geoId, {
						...geo,
						center: scp,
						start_angle: a,
						end_angle: b
					}, true);
					break;
				}
				case "Ellipse":
				case "ArcOfEllipse":
				case "ArcOfHyperbola": {
					const cp = geo.center, majdir = unit(geo.x_axis), A = geo.major_radius, B = geo.minor_radius;
					const df = geo.type === "ArcOfHyperbola" ? Math.sqrt(A * A + B * B) : Math.sqrt(A * A - B * B);
					const sf1 = m(add(cp, mul(majdir, df))), scp = m(cp);
					const x_axis = axisDir(sub(sf1, scp), majdir);
					if (geo.type === "Ellipse") {
						done(geoId, {
							...geo,
							center: scp,
							x_axis
						}, false);
						break;
					}
					let t1, t2;
					if (geo.type === "ArcOfEllipse") {
						t1 = TWO_PI - geo.start_angle;
						t2 = TWO_PI - geo.end_angle;
						[t1, t2] = [t2, t1];
						if (t1 < 0) {
							t1 += TWO_PI;
							t2 += TWO_PI;
						}
						[t1, t2] = setTrimPeriodic(t1, t2);
					} else {
						t1 = -geo.end_angle;
						t2 = -geo.start_angle;
					}
					done(geoId, stripEnds({
						...geo,
						center: scp,
						x_axis,
						start_angle: t1,
						end_angle: t2
					}), true);
					break;
				}
				case "ArcOfParabola": {
					const majdir = unit(geo.x_axis), sf1 = m(add(geo.center, mul(majdir, geo.focal))), scp = m(geo.center);
					done(geoId, stripEnds({
						...geo,
						center: scp,
						x_axis: axisDir(sub(sf1, scp), majdir),
						start_angle: -geo.end_angle,
						end_angle: -geo.start_angle
					}), true);
					break;
				}
				case "BSplineCurve":
					done(geoId, {
						...geo,
						poles: geo.poles.map(m),
						...geo.weights ? { weights: [...geo.weights] } : {},
						knots: [...geo.knots],
						mults: [...geo.mults]
					}, false);
					break;
				case "Point": done(geoId, {
					...geo,
					at: m(geo.at)
				}, false);
			}
		}
		return {
			geometry: out,
			geoIdMap,
			inverted
		};
	}
	const georef = geometryAt(d, refGeoId);
	let refpoint;
	if (georef?.type === "Point") refpoint = georef.at;
	else if (refGeoId === -1 && refPosId === 1) refpoint = [0, 0];
	else refpoint = pointOf(d, refGeoId, refPosId);
	const m = (p) => add(p, mul(sub(refpoint, p), 2));
	for (const geoId of geoIdList) {
		const geo = geometryAt(d, geoId);
		if (!geo || !shouldCopy(geoId)) continue;
		switch (geo.type) {
			case "LineSegment":
				done(geoId, {
					...geo,
					start: m(geo.start),
					end: m(geo.end)
				}, false);
				break;
			case "Circle":
				done(geoId, {
					...geo,
					center: m(geo.center)
				}, false);
				break;
			case "ArcOfCircle": {
				const ssp = m(pointOf(d, geoId, 1)), sep = m(pointOf(d, geoId, 2)), scp = m(geo.center);
				const [a, b] = setTrimPeriodic(fmod(Math.atan2(ssp[1] - scp[1], ssp[0] - scp[0]), TWO_PI), fmod(Math.atan2(sep[1] - scp[1], sep[0] - scp[0]), TWO_PI));
				done(geoId, {
					...geo,
					center: scp,
					start_angle: a,
					end_angle: b
				}, false);
				break;
			}
			case "Ellipse":
			case "ArcOfEllipse":
			case "ArcOfHyperbola": {
				const cp = geo.center, majdir = unit(geo.x_axis), A = geo.major_radius, B = geo.minor_radius;
				const df = geo.type === "ArcOfHyperbola" ? Math.sqrt(A * A + B * B) : Math.sqrt(A * A - B * B);
				const sf1 = m(add(cp, mul(majdir, df))), scp = m(cp);
				done(geoId, stripEnds({
					...geo,
					center: scp,
					x_axis: axisDir(sub(sf1, scp), majdir)
				}), false);
				break;
			}
			case "ArcOfParabola": {
				const majdir = unit(geo.x_axis), sf1 = m(add(geo.center, mul(majdir, geo.focal))), scp = m(geo.center);
				done(geoId, stripEnds({
					...geo,
					center: scp,
					x_axis: axisDir(sub(sf1, scp), majdir)
				}), false);
				break;
			}
			case "BSplineCurve":
				done(geoId, {
					...geo,
					poles: geo.poles.map(m),
					...geo.weights ? { weights: [...geo.weights] } : {},
					knots: [...geo.knots],
					mults: [...geo.mults]
				}, null);
				break;
			case "Point": done(geoId, {
				...geo,
				at: m(geo.at)
			}, false);
		}
	}
	return {
		geometry: out,
		geoIdMap,
		inverted
	};
}
/** SketchObject::addSymmetric(geoIdList, refGeoId, refPosId, addSymmetryConstraints): the mirror images added, with
*  the constraints among the mirrored elements copied (Python's sketch.addSymmetric leaves addSymmetryConstraints
*  false); with addSymmetryConstraints (the Symmetry tool's option) only the topological ones, and each mirrored point
*  tied to its original by a Symmetric constraint (a Coincident on the axis). Returns the last GeoId. */
function addSymmetric(d, geoIdList, refGeoId, refPosId = 0, addSymmetryConstraints = false) {
	const constrvals = d.constraints, newconstrVals = [...constrvals];
	const refIsAxisAligned = refGeoId === -2 || refGeoId === -1 || !(refPosId === 0) || constrvals.some((c) => c.first === refGeoId && (c.type === "Vertical" || c.type === "Horizontal"));
	const { geometry: symgeos0, geoIdMap, inverted } = getSymmetric(d, geoIdList, refGeoId, refPosId);
	const isInverted = (g) => inverted.get(g) ?? false;
	const symgeos = addSymmetryConstraints ? symgeos0.map((g) => {
		if (g.type !== "ArcOfCircle") return g;
		const [a, b] = setTrimPeriodic(g.start_angle + ANGULAR, g.end_angle);
		return {
			...g,
			start_angle: a,
			end_angle: b
		};
	}) : symgeos0;
	const original = {
		geometry: d.geometry,
		constraints: constrvals
	};
	d.geometry = [...d.geometry, ...symgeos];
	const flip = (g, pos) => isInverted(g) ? pos === 1 ? 2 : pos === 2 ? 1 : pos : pos;
	for (const constr of constrvals) {
		const first = geoIdMap.get(constr.first);
		if (first === void 0) continue;
		if (addSymmetryConstraints && constr.type !== "InternalAlignment") {
			if (!(constr.type === "Coincident" || (constr.type === "Tangent" || constr.type === "Perpendicular") && constr.firstPos !== 0 && constr.secondPos !== 0)) continue;
		}
		if (constr.second === -2e3) {
			if (refIsAxisAligned && (constr.type === "DistanceX" || constr.type === "DistanceY")) continue;
			if (!refIsAxisAligned && (constr.type === "DistanceX" || constr.type === "DistanceY" || constr.type === "Vertical" || constr.type === "Horizontal")) continue;
			newconstrVals.push({
				...constr,
				name: "",
				first
			});
			continue;
		}
		const second = geoIdMap.get(constr.second);
		if (second === void 0) continue;
		if (constr.third === -2e3) {
			if (![
				"Coincident",
				"Perpendicular",
				"Parallel",
				"Tangent",
				"Distance",
				"Equal",
				"Angle",
				"PointOnObject",
				"InternalAlignment"
			].includes(constr.type)) continue;
			const n = {
				...constr,
				name: "",
				first,
				firstPos: flip(constr.first, constr.firstPos),
				second,
				secondPos: flip(constr.second, constr.secondPos)
			};
			if (addSymmetryConstraints && (n.type === "Tangent" || n.type === "Perpendicular")) n.type = "Coincident";
			if (n.type === "Tangent" || n.type === "Perpendicular") n.value = 0;
			if (constr.type === "Angle" && refPosId === 0) n.value = -constr.value;
			newconstrVals.push(n);
			continue;
		}
		const third = geoIdMap.get(constr.third);
		if (third === void 0) continue;
		newconstrVals.push({
			...constr,
			name: "",
			first,
			firstPos: flip(constr.first, constr.firstPos),
			second,
			secondPos: flip(constr.second, constr.secondPos),
			third,
			thirdPos: flip(constr.third, constr.thirdPos)
		});
	}
	if (addSymmetryConstraints) {
		const constrained = /* @__PURE__ */ new Set();
		const key = (g, p) => `${g}:${p}`;
		const markPointConstrained = (g, p) => {
			constrained.add(key(g, p));
			for (const [mg, mp] of coincidentPoints(constrvals, g, p)) constrained.add(key(mg, mp));
		};
		const isPointOnReference = (pt) => {
			if (refPosId === 0) {
				const ref = geometryAt(original, refGeoId);
				if (ref?.type === "LineSegment") {
					const [l1, l2] = [ref.start, ref.end], dx = l2[0] - l1[0], dy = l2[1] - l1[1], lenSq = dx * dx + dy * dy;
					if (lenSq > CONFUSION * CONFUSION) {
						const area = (pt[0] - l1[0]) * dy - (pt[1] - l1[1]) * dx;
						if (Math.abs(area) / Math.sqrt(lenSq) < CONFUSION) return true;
					}
				}
			} else {
				const refPt = refGeoId === -1 ? [0, 0] : pointOf(original, refGeoId, refPosId);
				if (len(sub(pt, refPt)) < CONFUSION) return true;
			}
			return false;
		};
		const createSymConstr = (a, b, ap, bp) => {
			if (constrained.has(key(a, ap))) return;
			if (isPointOnReference(pointOf(original, a, ap))) newconstrVals.push(constraint("Coincident", a, ap, b, bp));
			else newconstrVals.push(constraint("Symmetric", a, ap, b, bp, refGeoId, refPosId));
			markPointConstrained(a, ap);
		};
		const createEquality = (a, b) => newconstrVals.push(constraint("Equal", a, 0, b, 0));
		for (const [g1, g2] of [...geoIdMap].sort((x, y) => x[0] - y[0])) {
			const geo = geometryAt(original, g1);
			const s = isInverted(g1) ? 2 : 1, e = isInverted(g1) ? 1 : 2;
			if (geo.type === "LineSegment") {
				if (!isInternalAligned(original, g1)) {
					createSymConstr(g1, g2, 1, s);
					createSymConstr(g1, g2, 2, e);
				}
			} else if (geo.type === "Circle" || geo.type === "Ellipse") {
				createEquality(g1, g2);
				createSymConstr(g1, g2, 3, 3);
			} else if (geo.type === "ArcOfCircle" || geo.type === "ArcOfEllipse" || geo.type === "ArcOfHyperbola" || geo.type === "ArcOfParabola") {
				createEquality(g1, g2);
				createSymConstr(g1, g2, 1, s);
				createSymConstr(g1, g2, 2, e);
			} else if (geo.type === "Point") {
				if (!isInternalAligned(original, g1)) createSymConstr(g1, g2, 1, 1);
			}
		}
	}
	d.constraints = newconstrVals;
	return d.geometry.length - 1;
}
/** Base::ValueError from addCopy, with FreeCAD's message. */
var XformError = class extends Error {};
const SINGLE_TO_EQUAL = [
	"DistanceX",
	"DistanceY",
	"Distance",
	"Diameter",
	"Weight",
	"Radius"
];
/** SketchObject::addCopy(geoIdList, displacement, moveonly, clone, csize, rsize, constraindisplacement, perpscale):
*  moves the geometry (moveonly), or copies it csize times along the displacement and rsize times across it (the
*  perpendicular displacement scaled by perpscale), each copy with the constraints among the copied elements (a clone
*  turns a dimension on one element into an Equal to the original, an angle into a Parallel) and a construction line
*  from the previous copy's reference point (the first element's start, or centre) dimensioned or tied to the first
*  one. FreeCAD 26.3 adds that line for a plain copy too, and constraindisplacement changes nothing. Returns the last
*  GeoId; throws an XformError when the first element is internal geometry without the geometry it defines. */
function addCopy(d, geoIdList, displacement, moveonly = false, clone = false, csize = 2, rsize = 1, constraindisplacement = false, perpscale = 1) {
	const geovals = d.geometry;
	const newgeoVals = [...geovals];
	const constrvals = d.constraints, newconstrVals = [...constrvals];
	const list = geoIdList.length ? [...geoIdList] : geovals.map((_, i) => i);
	let cgeoid = geovals.length;
	let iterfirstgeoid = -1, iterfirstpoint = [0, 0], refgeoid = -1, colrefgeoid = 0, rowrefgeoid = 0;
	let currentrowfirstgeoid = -1, prevrowstartfirstgeoid = -1, prevfirstgeoid = -1;
	let refposId = 0;
	const geoIdMap = /* @__PURE__ */ new Map();
	const perp = [perpscale * displacement[1], perpscale * -displacement[0]];
	const definedOf = (g) => {
		const c = constrvals.find((k) => k.type === "InternalAlignment" && k.first === g);
		return c ? c.second : GEO_UNDEF;
	};
	const internal = (g) => constrvals.some((k) => k.type === "InternalAlignment" && k.first === g);
	const original = {
		geometry: geovals,
		constraints: constrvals
	};
	const makeCopyAtRowColumn = (x, y) => {
		if (x === 0 && y === 0) {
			const g0 = list[0], geo = geometryAt(original, g0);
			if (internal(g0) && !moveonly && !list.includes(definedOf(g0))) throw new XformError("A move/copy/array operation on an internal alignment geometry is only possible together with the geometry it defines.");
			refgeoid = g0;
			currentrowfirstgeoid = refgeoid;
			iterfirstgeoid = refgeoid;
			refposId = geo.type === "Circle" || geo.type === "Ellipse" ? 3 : 1;
			return;
		}
		prevfirstgeoid = iterfirstgeoid;
		iterfirstgeoid = cgeoid;
		if (x === 0) {
			prevrowstartfirstgeoid = currentrowfirstgeoid;
			currentrowfirstgeoid = cgeoid;
		}
		const shift = (p) => add(add(p, mul(displacement, x)), mul(perp, y));
		list.forEach((g, k) => {
			const geo = moveonly && g >= 0 ? newgeoVals[g] : geometryAt(original, g);
			if (!geo) return;
			if (internal(g) && !moveonly && !list.includes(definedOf(g))) return;
			let copy;
			let firstPoint;
			switch (geo.type) {
				case "LineSegment":
					copy = {
						...geo,
						start: shift(geo.start),
						end: shift(geo.end)
					};
					firstPoint = copy.start;
					break;
				case "Circle":
					copy = {
						...geo,
						center: shift(geo.center)
					};
					firstPoint = copy.center;
					break;
				case "ArcOfCircle":
					copy = {
						...geo,
						center: shift(geo.center)
					};
					firstPoint = getPoint([copy], 0, 1);
					break;
				case "Ellipse":
					copy = {
						...geo,
						center: shift(geo.center)
					};
					firstPoint = copy.center;
					break;
				case "ArcOfEllipse":
				case "ArcOfHyperbola":
				case "ArcOfParabola":
					copy = stripEnds({
						...geo,
						center: shift(geo.center)
					});
					firstPoint = getPoint([copy], 0, 1);
					break;
				case "BSplineCurve":
					copy = {
						...geo,
						poles: geo.poles.map(shift),
						...geo.weights ? { weights: [...geo.weights] } : {},
						knots: [...geo.knots],
						mults: [...geo.mults]
					};
					firstPoint = getPoint([copy], 0, 1);
					break;
				case "Point":
					copy = {
						...geo,
						at: shift(geo.at)
					};
					firstPoint = copy.at;
					break;
				default: return;
			}
			if (k === 0) iterfirstpoint = firstPoint;
			if (moveonly) newgeoVals[g] = copy;
			else {
				newgeoVals.push(copy);
				if (!geoIdMap.has(g)) geoIdMap.set(g, cgeoid);
				cgeoid++;
			}
		});
		if (moveonly) return;
		for (const constr of constrvals) {
			const fit = geoIdMap.get(constr.first);
			if (fit === void 0) continue;
			if (constr.second === -2e3) {
				if ((constr.type === "DistanceX" || constr.type === "DistanceY") && constr.firstPos !== 0) continue;
				if (SINGLE_TO_EQUAL.includes(constr.type) && clone) {
					newconstrVals.push({
						...constr,
						type: "Equal",
						driving: true,
						second: fit
					});
					continue;
				}
				if (!(constr.type === "Angle" && clone)) {
					newconstrVals.push({
						...constr,
						first: fit
					});
					continue;
				}
				if (geometryAt(original, constr.first)?.type === "LineSegment") newconstrVals.push({
					...constr,
					type: "Parallel",
					driving: true,
					second: fit
				});
				continue;
			}
			const sit = geoIdMap.get(constr.second);
			if (sit === void 0) continue;
			if (constr.third === -2e3) {
				if ((constr.type === "DistanceX" || constr.type === "DistanceY" || constr.type === "Distance") && constr.first === constr.second && clone) {
					newconstrVals.push({
						...constr,
						type: "Equal",
						driving: true,
						firstPos: 0,
						second: fit,
						secondPos: 0
					});
					continue;
				}
				newconstrVals.push({
					...constr,
					first: fit,
					second: sit
				});
				continue;
			}
			if (geoIdMap.has(constr.third)) continue;
			newconstrVals.push({
				...constr,
				first: fit,
				second: sit,
				third: 0
			});
		}
		if (!constraindisplacement) geoIdMap.clear();
		const sp = add(pointOf(original, refgeoid, refposId), x === 0 ? add(mul(displacement, x), mul(perp, y - 1)) : add(mul(displacement, x - 1), mul(perp, y)));
		if (sp[0] === iterfirstpoint[0] && sp[1] === iterfirstpoint[1]) throw new XformError("Both points are equal");
		newgeoVals.push({
			type: "LineSegment",
			start: sp,
			end: iterfirstpoint,
			construction: true
		});
		if (x === 0) {
			newconstrVals.push(constraint("Coincident", prevrowstartfirstgeoid, refposId, cgeoid, 1));
			newconstrVals.push(constraint("Coincident", iterfirstgeoid, refposId, cgeoid, 2));
			if (y === 1) {
				rowrefgeoid = cgeoid;
				cgeoid++;
				if (perpscale === 1) newconstrVals.push(constraint("Equal", rowrefgeoid, 0, colrefgeoid, 0));
				else newconstrVals.push(constraint("Distance", rowrefgeoid, 0, GEO_UNDEF, 0, GEO_UNDEF, 0, len(perp)));
				newconstrVals.push(constraint("Perpendicular", rowrefgeoid, 0, colrefgeoid, 0));
			} else {
				cgeoid++;
				newconstrVals.push(constraint("Equal", rowrefgeoid, 0, cgeoid - 1, 0));
				newconstrVals.push(constraint("Perpendicular", cgeoid - 1, 0, colrefgeoid, 0));
			}
		} else {
			newconstrVals.push(constraint("Coincident", prevfirstgeoid, refposId, cgeoid, 1));
			newconstrVals.push(constraint("Coincident", iterfirstgeoid, refposId, cgeoid, 2));
			if (y === 0 && x === 1) {
				colrefgeoid = cgeoid;
				cgeoid++;
				newconstrVals.push(constraint("Distance", colrefgeoid, 0, GEO_UNDEF, 0, GEO_UNDEF, 0, len(displacement)));
				newconstrVals.push(constraint("Angle", colrefgeoid, 0, GEO_UNDEF, 0, GEO_UNDEF, 0, Math.atan2(displacement[1], displacement[0])));
			} else {
				cgeoid++;
				newconstrVals.push(constraint("Equal", colrefgeoid, 0, cgeoid - 1, 0));
				newconstrVals.push(constraint("Parallel", cgeoid - 1, 0, colrefgeoid, 0));
			}
		}
		geoIdMap.clear();
	};
	for (let y = 0; y < rsize; y++) for (let x = 0; x < csize; x++) makeCopyAtRowColumn(x, y);
	d.geometry = newgeoVals;
	d.constraints = newconstrVals;
	return d.geometry.length - 1;
}
/** sketch.addMove(geoIds, vector): addCopy moving the geometry in place (no constraint changes, no solve). */
const addMove = (d, geoIdList, displacement) => addCopy(d, geoIdList, displacement, true);
/** sketch.addRectangularArray(geoIds, vector, clone, rows, cols, constrainDisplacement, perpScale): addCopy with csize
*  the Python's rows and rsize its cols (the Rectangular Array tool passes its columns as rows). */
const addRectangularArray = (d, geoIdList, displacement, clone, rows, cols, constrainDisplacement = false, perpscale = 1) => addCopy(d, geoIdList, displacement, false, clone, rows, cols, constrainDisplacement, perpscale);
/** SketchObject::removeAxesAlignment(geoIdList): on the constraints touching the elements, the first Horizontal (and
*  the first Vertical) of a line goes and the next ones become Parallel to its line, a Symmetric about an axis and a
*  point on an axis go, and a DistanceX / DistanceY becomes a Distance. True when something changed. */
function removeAxesAlignment(d, geoIdList) {
	if (!geoIdList.length) return false;
	const out = [];
	let changed = false;
	const reference = {
		Horizontal: GEO_UNDEF,
		Vertical: GEO_UNDEF
	};
	for (const c of d.constraints) {
		if (!geoIdList.some((g) => c.first === g || c.second === g || c.third === g)) {
			out.push(c);
			continue;
		}
		switch (c.type) {
			case "Horizontal":
			case "Vertical":
				if (c.firstPos === 0 && c.secondPos === 0) {
					changed = true;
					if (reference[c.type] === -2e3) reference[c.type] = c.first;
					else out.push(constraint("Parallel", reference[c.type], 0, c.first, 0));
				} else out.push(c);
				break;
			case "Symmetric":
				if ((c.third === -1 || c.third === -2) && c.thirdPos === 0) changed = true;
				else out.push(c);
				break;
			case "PointOnObject":
				if ((c.second === -1 || c.second === -2) && c.secondPos === 0) changed = true;
				else out.push(c);
				break;
			case "DistanceX":
			case "DistanceY":
				changed = true;
				out.push({
					...c,
					type: "Distance"
				});
				break;
			default: out.push(c);
		}
	}
	if (changed) d.constraints = out;
	return changed;
}
//#endregion
//#region ui/scripts/sketchxform-entry.ts
const DIMENSIONAL = [
	"Distance",
	"DistanceX",
	"DistanceY",
	"Radius",
	"Diameter",
	"Angle",
	"Weight"
];
function toConstraint(r) {
	const [f, fp, s, sp, t, tp] = r.elements;
	const c = constraint(r.type, f, fp, s, sp, t, tp, DIMENSIONAL.includes(r.type) ? r.value ?? 0 : 0);
	if (r.type === "InternalAlignment") {
		c.alignment = r.alignment;
		c.alignmentIndex = r.index ?? -1;
	}
	c.name = r.name;
	c.driving = r.driving;
	return c;
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
		],
		name: c.name,
		driving: c.driving
	};
	if (c.type === "InternalAlignment") {
		d.alignment = c.alignment ?? "Undef";
		d.index = c.alignmentIndex ?? -1;
	}
	if (DIMENSIONAL.includes(c.type)) d.value = c.value;
	return d;
}
function runCase(c) {
	const input = c.freecad.input;
	if (!input) return { error: "FreeCAD could not make the sketch" };
	const doc = {
		geometry: input.geometry.map((g, i) => {
			const { start_point: _s, end_point: _e, ...rest } = g;
			return input.constructions[i] ? {
				...rest,
				construction: true
			} : rest;
		}),
		constraints: input.constraints.map(toConstraint)
	};
	const [op, args] = c.op;
	let ok = true;
	try {
		if (op === "symmetric") {
			const [ids, ref, pos] = args;
			addSymmetric(doc, ids, ref, pos);
		} else if (op === "copy") {
			const [ids, v, clone] = args;
			addCopy(doc, ids, v, false, clone);
		} else if (op === "move") {
			const [ids, v] = args;
			addMove(doc, ids, v);
		} else if (op === "array") {
			const [ids, v, clone, rows, cols, disp, perp] = args;
			addRectangularArray(doc, ids, v, clone, rows, cols, disp, perp);
		} else if (op === "removeAxes") {
			const [ids] = args;
			removeAxesAlignment(doc, ids);
		}
	} catch (e) {
		ok = String(e);
	}
	return {
		ok,
		geometry: doc.geometry.map((g) => {
			const { construction: _c, ...rest } = g;
			return rest;
		}),
		constructions: doc.geometry.map((g) => !!g.construction),
		constraints: doc.constraints.map(out)
	};
}
//#endregion
export { runCase };
