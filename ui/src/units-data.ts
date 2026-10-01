// FreeCAD's units, generated from src/Base/Quantity.l, Quantity.cpp, Unit.cpp and
// UnitsConvData.h at FreeCAD main 3160daf1e2b6 (LGPL-2.1-or-later). Internal units are
// FreeCAD's: mm, kg, s, A, K, mol, cd, degree. Dimensions are exponents of those eight.
export type Dims = [number, number, number, number, number, number, number, number]
/** Each token the quantity lexer knows: its value in internal units and its dimensions. */
export const UNITS: Record<string, [number, Dims]> = {
  "nm": [1e-06, [1, 0, 0, 0, 0, 0, 0, 0]], // NanoMetre
  "um": [0.001, [1, 0, 0, 0, 0, 0, 0, 0]], // MicroMetre
  "µm": [0.001, [1, 0, 0, 0, 0, 0, 0, 0]], // MicroMetre
  "mm": [1.0, [1, 0, 0, 0, 0, 0, 0, 0]], // MilliMetre
  "cm": [10.0, [1, 0, 0, 0, 0, 0, 0, 0]], // CentiMetre
  "dm": [100.0, [1, 0, 0, 0, 0, 0, 0, 0]], // DeciMetre
  "m": [1000.0, [1, 0, 0, 0, 0, 0, 0, 0]], // Metre
  "km": [1000000.0, [1, 0, 0, 0, 0, 0, 0, 0]], // KiloMetre
  "l": [1000000.0, [3, 0, 0, 0, 0, 0, 0, 0]], // Liter
  "ml": [1000.0, [3, 0, 0, 0, 0, 0, 0, 0]], // MilliLiter
  "Hz": [1.0, [0, 0, -1, 0, 0, 0, 0, 0]], // Hertz
  "kHz": [1000.0, [0, 0, -1, 0, 0, 0, 0, 0]], // KiloHertz
  "MHz": [1000000.0, [0, 0, -1, 0, 0, 0, 0, 0]], // MegaHertz
  "GHz": [1000000000.0, [0, 0, -1, 0, 0, 0, 0, 0]], // GigaHertz
  "THz": [1000000000000.0, [0, 0, -1, 0, 0, 0, 0, 0]], // TeraHertz
  "ug": [1e-09, [0, 1, 0, 0, 0, 0, 0, 0]], // MicroGram
  "µg": [1e-09, [0, 1, 0, 0, 0, 0, 0, 0]], // MicroGram
  "mg": [1e-06, [0, 1, 0, 0, 0, 0, 0, 0]], // MilliGram
  "g": [0.001, [0, 1, 0, 0, 0, 0, 0, 0]], // Gram
  "kg": [1.0, [0, 1, 0, 0, 0, 0, 0, 0]], // KiloGram
  "t": [1000.0, [0, 1, 0, 0, 0, 0, 0, 0]], // Ton
  "s": [1.0, [0, 0, 1, 0, 0, 0, 0, 0]], // Second
  "min": [60.0, [0, 0, 1, 0, 0, 0, 0, 0]], // Minute
  "h": [3600.0, [0, 0, 1, 0, 0, 0, 0, 0]], // Hour
  "A": [1.0, [0, 0, 0, 1, 0, 0, 0, 0]], // Ampere
  "nA": [1e-09, [0, 0, 0, 1, 0, 0, 0, 0]], // NanoAmpere
  "uA": [1e-06, [0, 0, 0, 1, 0, 0, 0, 0]], // MicroAmpere
  "mA": [0.001, [0, 0, 0, 1, 0, 0, 0, 0]], // MilliAmpere
  "kA": [1000.0, [0, 0, 0, 1, 0, 0, 0, 0]], // KiloAmpere
  "MA": [1000000.0, [0, 0, 0, 1, 0, 0, 0, 0]], // MegaAmpere
  "K": [1.0, [0, 0, 0, 0, 1, 0, 0, 0]], // Kelvin
  "mK": [0.001, [0, 0, 0, 0, 1, 0, 0, 0]], // MilliKelvin
  "µK": [1e-06, [0, 0, 0, 0, 1, 0, 0, 0]], // MicroKelvin
  "uK": [1e-06, [0, 0, 0, 0, 1, 0, 0, 0]], // MicroKelvin
  "mol": [1.0, [0, 0, 0, 0, 0, 1, 0, 0]], // Mole
  "nmol": [1e-09, [0, 0, 0, 0, 0, 1, 0, 0]], // NanoMole
  "umol": [1e-06, [0, 0, 0, 0, 0, 1, 0, 0]], // MicroMole
  "µmol": [1e-06, [0, 0, 0, 0, 0, 1, 0, 0]], // MicroMole
  "mmol": [0.001, [0, 0, 0, 0, 0, 1, 0, 0]], // MilliMole
  "cd": [1.0, [0, 0, 0, 0, 0, 0, 1, 0]], // Candela
  "in": [25.4, [1, 0, 0, 0, 0, 0, 0, 0]], // Inch
  "\"": [25.4, [1, 0, 0, 0, 0, 0, 0, 0]], // Inch
  "ft": [304.79999999999995, [1, 0, 0, 0, 0, 0, 0, 0]], // Foot
  "'": [304.79999999999995, [1, 0, 0, 0, 0, 0, 0, 0]], // Foot
  "thou": [0.0254, [1, 0, 0, 0, 0, 0, 0, 0]], // Thou
  "mil": [0.0254, [1, 0, 0, 0, 0, 0, 0, 0]], // Thou
  "yd": [914.3999999999999, [1, 0, 0, 0, 0, 0, 0, 0]], // Yard
  "mi": [1609343.9999999998, [1, 0, 0, 0, 0, 0, 0, 0]], // Mile
  "mph": [447.03999999999996, [1, 0, -1, 0, 0, 0, 0, 0]], // MilePerHour
  "sqft": [92903.03999999998, [2, 0, 0, 0, 0, 0, 0, 0]], // SquareFoot
  "cft": [28316846.59199999, [3, 0, 0, 0, 0, 0, 0, 0]], // CubicFoot
  "lb": [0.45359237, [0, 1, 0, 0, 0, 0, 0, 0]], // Pound
  "lbm": [0.45359237, [0, 1, 0, 0, 0, 0, 0, 0]], // Pound
  "oz": [0.028349523125, [0, 1, 0, 0, 0, 0, 0, 0]], // Ounce
  "st": [6.35029318, [0, 1, 0, 0, 0, 0, 0, 0]], // Stone
  "cwt": [50.80234544, [0, 1, 0, 0, 0, 0, 0, 0]], // Hundredweights
  "lbf": [4448.2216152605, [1, 1, -2, 0, 0, 0, 0, 0]], // PoundForce
  "N": [1000.0, [1, 1, -2, 0, 0, 0, 0, 0]], // Newton
  "mN": [1.0, [1, 1, -2, 0, 0, 0, 0, 0]], // MilliNewton
  "kN": [1000000.0, [1, 1, -2, 0, 0, 0, 0, 0]], // KiloNewton
  "MN": [1000000000.0, [1, 1, -2, 0, 0, 0, 0, 0]], // MegaNewton
  "Pa": [0.001, [-1, 1, -2, 0, 0, 0, 0, 0]], // Pascal
  "kPa": [1.0, [-1, 1, -2, 0, 0, 0, 0, 0]], // KiloPascal
  "MPa": [1000.0, [-1, 1, -2, 0, 0, 0, 0, 0]], // MegaPascal
  "GPa": [1000000.0, [-1, 1, -2, 0, 0, 0, 0, 0]], // GigaPascal
  "bar": [100.0, [-1, 1, -2, 0, 0, 0, 0, 0]], // Bar
  "mbar": [0.1, [-1, 1, -2, 0, 0, 0, 0, 0]], // MilliBar
  "Torr": [0.13332236842105263, [-1, 1, -2, 0, 0, 0, 0, 0]], // Torr
  "mTorr": [0.00013332236842105263, [-1, 1, -2, 0, 0, 0, 0, 0]], // mTorr
  "uTorr": [1.3332236842105263e-07, [-1, 1, -2, 0, 0, 0, 0, 0]], // yTorr
  "µTorr": [1.3332236842105263e-07, [-1, 1, -2, 0, 0, 0, 0, 0]], // yTorr
  "psi": [6.894757293168361, [-1, 1, -2, 0, 0, 0, 0, 0]], // PSI
  "ksi": [6894.757293168361, [-1, 1, -2, 0, 0, 0, 0, 0]], // KSI
  "Mpsi": [6894757.293168361, [-1, 1, -2, 0, 0, 0, 0, 0]], // MPSI
  "W": [1000000.0, [2, 1, -3, 0, 0, 0, 0, 0]], // Watt
  "nW": [0.001, [2, 1, -3, 0, 0, 0, 0, 0]], // NanoWatt
  "uW": [1.0, [2, 1, -3, 0, 0, 0, 0, 0]], // MicroWatt
  "µW": [1.0, [2, 1, -3, 0, 0, 0, 0, 0]], // MicroWatt
  "mW": [1000.0, [2, 1, -3, 0, 0, 0, 0, 0]], // MilliWatt
  "kW": [1000000000.0, [2, 1, -3, 0, 0, 0, 0, 0]], // KiloWatt
  "VA": [1000000.0, [2, 1, -3, 0, 0, 0, 0, 0]], // VoltAmpere
  "V": [1000000.0, [2, 1, -3, -1, 0, 0, 0, 0]], // Volt
  "kV": [1000000000.0, [2, 1, -3, -1, 0, 0, 0, 0]], // KiloVolt
  "mV": [1000.0, [2, 1, -3, -1, 0, 0, 0, 0]], // MilliVolt
  "MS": [1.0, [-2, -1, 3, 2, 0, 0, 0, 0]], // MegaSiemens
  "kS": [0.001, [-2, -1, 3, 2, 0, 0, 0, 0]], // KiloSiemens
  "S": [1e-06, [-2, -1, 3, 2, 0, 0, 0, 0]], // Siemens
  "mS": [1e-09, [-2, -1, 3, 2, 0, 0, 0, 0]], // MilliSiemens
  "µS": [1e-12, [-2, -1, 3, 2, 0, 0, 0, 0]], // MicroSiemens
  "uS": [1e-12, [-2, -1, 3, 2, 0, 0, 0, 0]], // MicroSiemens
  "Ohm": [1000000.0, [2, 1, -3, -2, 0, 0, 0, 0]], // Ohm
  "kOhm": [1000000000.0, [2, 1, -3, -2, 0, 0, 0, 0]], // KiloOhm
  "MOhm": [1000000000000.0, [2, 1, -3, -2, 0, 0, 0, 0]], // MegaOhm
  "C": [1.0, [0, 0, 1, 1, 0, 0, 0, 0]], // Coulomb
  "T": [1.0, [0, 1, -2, -1, 0, 0, 0, 0]], // Tesla
  "mT": [0.001, [0, 1, -2, -1, 0, 0, 0, 0]], // MilliTesla
  "G": [0.0001, [0, 1, -2, -1, 0, 0, 0, 0]], // Gauss
  "Wb": [1000000.0, [2, 1, -2, -1, 0, 0, 0, 0]], // Weber
  "F": [1e-06, [-2, -1, 4, 2, 0, 0, 0, 0]], // Farad
  "mF": [1e-09, [-2, -1, 4, 2, 0, 0, 0, 0]], // MilliFarad
  "µF": [1e-12, [-2, -1, 4, 2, 0, 0, 0, 0]], // MicroFarad
  "uF": [1e-12, [-2, -1, 4, 2, 0, 0, 0, 0]], // MicroFarad
  "nF": [1e-15, [-2, -1, 4, 2, 0, 0, 0, 0]], // NanoFarad
  "pF": [1e-18, [-2, -1, 4, 2, 0, 0, 0, 0]], // PicoFarad
  "H": [1000000.0, [2, 1, -2, -2, 0, 0, 0, 0]], // Henry
  "mH": [1000.0, [2, 1, -2, -2, 0, 0, 0, 0]], // MilliHenry
  "µH": [1.0, [2, 1, -2, -2, 0, 0, 0, 0]], // MicroHenry
  "uH": [1.0, [2, 1, -2, -2, 0, 0, 0, 0]], // MicroHenry
  "nH": [0.001, [2, 1, -2, -2, 0, 0, 0, 0]], // NanoHenry
  "J": [1000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // Joule
  "mJ": [1000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // MilliJoule
  "kJ": [1000000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // KiloJoule
  "Nm": [1000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // NewtonMeter
  "Nmm": [1000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // NewtonMilliMeter
  "VAs": [1000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // VoltAmpereSecond
  "CV": [1000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // WattSecond
  "Ws": [1000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // WattSecond
  "kWh": [3600000000000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // KiloWattHour
  "eV": [1.602176634e-13, [2, 1, -2, 0, 0, 0, 0, 0]], // ElectronVolt
  "keV": [1.602176634e-10, [2, 1, -2, 0, 0, 0, 0, 0]], // KiloElectronVolt
  "MeV": [1.602176634e-07, [2, 1, -2, 0, 0, 0, 0, 0]], // MegaElectronVolt
  "cal": [4186800.0, [2, 1, -2, 0, 0, 0, 0, 0]], // Calorie
  "kcal": [4186800000.0, [2, 1, -2, 0, 0, 0, 0, 0]], // KiloCalorie
  "°": [1.0, [0, 0, 0, 0, 0, 0, 0, 1]], // Degree
  "deg": [1.0, [0, 0, 0, 0, 0, 0, 0, 1]], // Degree
  "rad": [57.29577951308232, [0, 0, 0, 0, 0, 0, 0, 1]], // Radian
  "gon": [0.9, [0, 0, 0, 0, 0, 0, 0, 1]], // Gon
  "M": [0.016666666666666666, [0, 0, 0, 0, 0, 0, 0, 1]], // AngMinute
  "′": [0.016666666666666666, [0, 0, 0, 0, 0, 0, 0, 1]], // AngMinute
  "AS": [0.0002777777777777778, [0, 0, 0, 0, 0, 0, 0, 1]], // AngSecond
  "″": [0.0002777777777777778, [0, 0, 0, 0, 0, 0, 0, 1]], // AngSecond
}
/** Unit::getTypeString: the named quantity types, first match wins. */
export const UNIT_TYPES: [string, Dims][] = [
  ["1", [0, 0, 0, 0, 0, 0, 0, 0]],
  ["Length", [1, 0, 0, 0, 0, 0, 0, 0]],
  ["Mass", [0, 1, 0, 0, 0, 0, 0, 0]],
  ["TimeSpan", [0, 0, 1, 0, 0, 0, 0, 0]],
  ["ElectricCurrent", [0, 0, 0, 1, 0, 0, 0, 0]],
  ["Temperature", [0, 0, 0, 0, 1, 0, 0, 0]],
  ["AmountOfSubstance", [0, 0, 0, 0, 0, 1, 0, 0]],
  ["LuminousIntensity", [0, 0, 0, 0, 0, 0, 1, 0]],
  ["Angle", [0, 0, 0, 0, 0, 0, 0, 1]],
  ["Acceleration", [1, 0, -2, 0, 0, 0, 0, 0]],
  ["AngleOfFriction", [0, 0, 0, 0, 0, 0, 0, 1]],
  ["Area", [2, 0, 0, 0, 0, 0, 0, 0]],
  ["CurrentDensity", [-2, 0, 0, 1, 0, 0, 0, 0]],
  ["Density", [-3, 1, 0, 0, 0, 0, 0, 0]],
  ["DissipationRate", [2, 0, -3, 0, 0, 0, 0, 0]],
  ["DynamicViscosity", [-1, 1, -1, 0, 0, 0, 0, 0]],
  ["ElectricalCapacitance", [-2, -1, 4, 2, 0, 0, 0, 0]],
  ["ElectricalConductance", [-2, -1, 3, 2, 0, 0, 0, 0]],
  ["ElectricalConductivity", [-3, -1, 3, 2, 0, 0, 0, 0]],
  ["ElectricalInductance", [2, 1, -2, -2, 0, 0, 0, 0]],
  ["ElectricalResistance", [2, 1, -3, -2, 0, 0, 0, 0]],
  ["ElectricCharge", [0, 0, 1, 1, 0, 0, 0, 0]],
  ["ElectricPotential", [2, 1, -3, -1, 0, 0, 0, 0]],
  ["ElectromagneticPotential", [1, 1, -2, -1, 0, 0, 0, 0]],
  ["Force", [1, 1, -2, 0, 0, 0, 0, 0]],
  ["Frequency", [0, 0, -1, 0, 0, 0, 0, 0]],
  ["HeatFlux", [0, 1, -3, 0, 0, 0, 0, 0]],
  ["MassMomentOfInertia", [2, 1, 0, 0, 0, 0, 0, 0]],
  ["AreaMomentOfInertia", [4, 0, 0, 0, 0, 0, 0, 0]],
  ["InverseArea", [-2, 0, 0, 0, 0, 0, 0, 0]],
  ["InverseLength", [-1, 0, 0, 0, 0, 0, 0, 0]],
  ["InverseVolume", [-3, 0, 0, 0, 0, 0, 0, 0]],
  ["KinematicViscosity", [2, 0, -1, 0, 0, 0, 0, 0]],
  ["MagneticFieldStrength", [-1, 0, 0, 1, 0, 0, 0, 0]],
  ["MagneticFlux", [2, 1, -2, -1, 0, 0, 0, 0]],
  ["MagneticFluxDensity", [0, 1, -2, -1, 0, 0, 0, 0]],
  ["Magnetization", [-1, 0, 0, 1, 0, 0, 0, 0]],
  ["Moment", [2, 1, -2, 0, 0, 0, 0, 0]],
  ["Pressure", [-1, 1, -2, 0, 0, 0, 0, 0]],
  ["Power", [2, 1, -3, 0, 0, 0, 0, 0]],
  ["ShearModulus", [-1, 1, -2, 0, 0, 0, 0, 0]],
  ["SpecificEnergy", [2, 0, -2, 0, 0, 0, 0, 0]],
  ["SpecificHeat", [2, 0, -2, 0, -1, 0, 0, 0]],
  ["Stiffness", [0, 1, -2, 0, 0, 0, 0, 0]],
  ["StiffnessDensity", [-2, 1, -2, 0, 0, 0, 0, 0]],
  ["Stress", [-1, 1, -2, 0, 0, 0, 0, 0]],
  ["SurfaceChargeDensity", [-2, 0, 1, 1, 0, 0, 0, 0]],
  ["ThermalConductivity", [1, 1, -3, 0, -1, 0, 0, 0]],
  ["ThermalExpansionCoefficient", [0, 0, 0, 0, -1, 0, 0, 0]],
  ["ThermalTransferCoefficient", [0, 1, -3, 0, -1, 0, 0, 0]],
  ["UltimateTensileStrength", [-1, 1, -2, 0, 0, 0, 0, 0]],
  ["VacuumPermittivity", [-3, -1, 4, 2, 0, 0, 0, 0]],
  ["Velocity", [1, 0, -1, 0, 0, 0, 0, 0]],
  ["Volume", [3, 0, 0, 0, 0, 0, 0, 0]],
  ["Concentration", [-3, 0, 0, 0, 0, 1, 0, 0]],
  ["VolumeChargeDensity", [-3, 0, 1, 1, 0, 0, 0, 0]],
  ["VolumeFlowRate", [3, 0, -1, 0, 0, 0, 0, 0]],
  ["VolumetricThermalExpansionCoefficient", [0, 0, 0, 0, -1, 0, 0, 0]],
  ["Work", [2, 1, -2, 0, 0, 0, 0, 0]],
  ["YieldStrength", [-1, 1, -2, 0, 0, 0, 0, 0]],
  ["YoungsModulus", [-1, 1, -2, 0, 0, 0, 0, 0]],
]
