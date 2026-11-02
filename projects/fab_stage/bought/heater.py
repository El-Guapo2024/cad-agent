"""heater: Tempco MSH00072 mica strip/plate heater, 177.8 x 292.1, 625 W at 120 V

Bought part, an envelope: a flat plate clamped under the platen by the clamp plate. Its thickness is not on
Tempco's catalog page: 4.5 is Misumi's MPHK mica heater thickness (T 4.0 to 4.5), so UNVERIFIED until one is
measured. Tempco rates its mica strip heaters' rust-resistant steel sheath to 900 F (480 C).
"""
from build123d import Box

SOURCE = "Tempco catalog page 8-24, MSH00072 mica strip/plate heater 7 x 11.5 in (177.8 x 292.1), 625 W, 120 V: https://www.tempco.com/Tempco/Resources/Individual-Catalog-Pages/8-24.pdf ; thickness from Misumi MPHK (https://jp.misumi-ec.com/vona2/detail/110300386520/)"
VENDOR = "Tempco"
VERIFIED = False
MAX_TEMP_C = 480.0
MAX_TEMP_SOURCE = "Tempco mica insulated strip heaters spec sheet: maximum sheath temperature, rust resistant steel 900 F (480 C): https://www.im-tek.com/docs/tempco-mica-insulated-strip-heaters-655735.pdf"

PARAMS = {"size_x": 177.8, "size_y": 292.1, "thick": 4.5}


def build(size_x, size_y, thick):
    return Box(size_x, size_y, thick)
