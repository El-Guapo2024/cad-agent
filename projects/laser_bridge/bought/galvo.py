"""galvo: Sino-Galvo

Bought part. Its output (underside, 45 from the input end) is drawn as the M85 x 1 seat the lens's input end
screws 26.6 into (Jenoptik's STEP: 22.5 to 49.1 above its flange). The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'SG7110 10 mm aperture galvo head with high-reflectance UV (355 nm) mirrors, as in JPT Lark UV marking machines (https://haotianlasers.com/product/uv-laser-marking-machine-5w/); body 118.5 x 96.5 x 93.6 mm, about 1.65 kg, 355 nm among its wavelengths, per https://bestsuppliers.com/products/mentfcbyzgr9/high-quality-sg7110-sg7210-jd2206-galvo-scan-head-zbtk-galvanometer-scanner-for-fiber-laser-marking'
VENDOR = 'Sino-Galvo'
VERIFIED = False
MASS_G = 1650.0
MASS_SOURCE = 'SG7110 listing (bestsuppliers.com, in SOURCE): about 1.65 kg'

PARAMS = {'length': 118.5, 'width': 96.5, 'height': 93.6, 'out_x': -14.25, 'out_dia': 85.2, 'out_depth': 26.7}


def build(length, width, height, out_x, out_dia, out_depth):
    body = Box(length, width, height)
    body -= Pos(out_x, 0, -height / 2.0 + out_depth / 2.0) * Cylinder(out_dia / 2.0, out_depth)   # the output's M85 seat

    return body
