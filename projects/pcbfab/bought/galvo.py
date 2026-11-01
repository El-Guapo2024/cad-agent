"""galvo: Sino-Galvo

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'SG7110 10 mm aperture galvo head with high-reflectance UV (355 nm) mirrors, as in JPT Lark UV marking machines (https://haotianlasers.com/product/uv-laser-marking-machine-5w/); body 118.5 x 96.5 x 93.6 mm, about 1.65 kg, 355 nm among its wavelengths, per https://bestsuppliers.com/products/mentfcbyzgr9/high-quality-sg7110-sg7210-jd2206-galvo-scan-head-zbtk-galvanometer-scanner-for-fiber-laser-marking'
VENDOR = 'Sino-Galvo'
VERIFIED = False

PARAMS = {'length': 118.5, 'width': 96.5, 'height': 93.6}


def build(length, width, height):
    body = Box(length, width, height)

    return body
