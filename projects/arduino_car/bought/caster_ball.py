"""Loose steel ball for the caster socket.

A bearing ball, sold by diameter to a published tolerance, which is the one
bought part in this project whose dimension needs no confirming: 16 mm means
16 mm within a few microns. That is why this is the only bought module here
marked verified.
"""
from build123d import Sphere

SOURCE = "standard bearing ball, nominal diameter is the specification"
VENDOR = None
VERIFIED = True

PARAMS = {"dia": 16.0}


def build(dia):
    return Sphere(dia / 2.0)
