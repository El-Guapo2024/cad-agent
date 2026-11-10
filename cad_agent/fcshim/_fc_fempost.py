# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's FemPostPipeline reading (src/Mod/Fem/App/FemPostPipeline.cpp, FemPostPipelinePyImp.cpp;
# Copyright (c) 2015 Stefan Tröger), over VTK's Python (the `vtk` package, BSD-3-Clause), as FreeCAD's own VTK reads.
"""Fem::FemPostPipeline's Data from result files: FemPostPipeline::dataObjectFromFile by the file's extension, read()
of several files as a vtkMultiBlockDataSet of frames (each with its TimeValue, and the TimeInfo of frame type and
unit), readPVD and setTimeInfo."""
from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET


def _readers():
    from vtkmodules.vtkIOLegacy import vtkDataSetReader
    from vtkmodules.vtkIOXML import (vtkXMLImageDataReader, vtkXMLMultiBlockDataReader, vtkXMLPolyDataReader,
                                     vtkXMLPUnstructuredGridReader, vtkXMLRectilinearGridReader,
                                     vtkXMLStructuredGridReader, vtkXMLUnstructuredGridReader)
    return {".vtu": vtkXMLUnstructuredGridReader, ".pvtu": vtkXMLPUnstructuredGridReader, ".vtp": vtkXMLPolyDataReader,
            ".vts": vtkXMLStructuredGridReader, ".vtr": vtkXMLRectilinearGridReader, ".vti": vtkXMLImageDataReader,
            ".vtk": vtkDataSetReader, ".vtm": vtkXMLMultiBlockDataReader}


def data_object(path):
    """FemPostPipeline::dataObjectFromFile."""
    path = str(path)
    if not os.access(path, os.R_OK):
        raise OSError(f"File to load not existing or not readable: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pvd":
        return _read_pvd(path)
    readers = _readers()
    if ext not in readers:
        raise OSError("Unknown extension")
    r = readers[ext]()
    r.SetFileName(path)
    r.Update()
    return r.GetOutputDataObject(0)


def _time_info(frame_type, unit):
    from vtkmodules.vtkCommonCore import vtkStringArray
    t = vtkStringArray()
    t.SetName("TimeInfo")
    t.InsertNextValue(frame_type)
    t.InsertNextValue(unit)
    return t


def _time_value(v):
    from vtkmodules.vtkCommonCore import vtkFloatArray
    t = vtkFloatArray()
    t.SetNumberOfComponents(1)
    t.SetName("TimeValue")
    t.InsertNextValue(v)
    return t


def _read_pvd(path):
    """FemPostPipeline::readPVD: each DataSet's file at its timestep, in timestep order."""
    from vtkmodules.vtkCommonDataModel import vtkMultiBlockDataSet
    values = {}
    for e in ET.parse(path).getroot().iter("DataSet"):
        values.setdefault(float(e.get("timestep")), e.get("file"))
    info = _time_info("TimeStep", "")
    mb = vtkMultiBlockDataSet()
    mb.GetFieldData().AddArray(info)
    for i, (t, f) in enumerate(sorted(values.items())):
        d = data_object(os.path.join(os.path.dirname(path), f))
        d.GetFieldData().AddArray(_time_value(t))
        d.GetFieldData().AddArray(info)
        mb.SetBlock(i, d)
    return mb


def _unit_string(unit):
    return unit if isinstance(unit, str) else (unit.getString() if hasattr(unit, "getString") else str(unit))


def read(files, values=None, unit=None, frame_type=None):
    """FemPostPipelinePy::read: a file, or the files with their frame values, unit and frame type."""
    if values is None:
        return data_object(files)
    from vtkmodules.vtkCommonDataModel import vtkMultiBlockDataSet
    files, values = list(files), [float(v) for v in values]
    if len(files) != len(values):
        raise ValueError("Result files and frame values have different length")
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Values need to be finite")
    if len(set(values)) != len(values):
        raise ValueError("Values need to be unique")
    info = _time_info(frame_type or "", _unit_string(unit) if unit is not None else "")
    mb = vtkMultiBlockDataSet()
    for i, (f, v) in enumerate(zip(files, values)):
        d = data_object(f)
        d.GetFieldData().AddArray(_time_value(v))
        d.GetFieldData().AddArray(info)
        mb.SetBlock(i, d)
    mb.GetFieldData().AddArray(info)
    return mb


def set_time_info(data, frame_type, unit):
    """FemPostPipeline::setTimeInfo: the multiblock's and each frame's TimeInfo."""
    if data is None or not data.IsA("vtkMultiBlockDataSet"):
        return
    info = _time_info(frame_type, _unit_string(unit))
    data.GetFieldData().AddArray(info)
    for i in range(data.GetNumberOfBlocks()):
        b = data.GetBlock(i)
        if b is not None:
            b.GetFieldData().AddArray(info)


def frame_values(data):
    """The frames' TimeValue (FemPostPipeline::getFrameValues, of a multiblock's frames), else none."""
    if data is None or not data.IsA("vtkMultiBlockDataSet"):
        return []
    out = []
    for i in range(data.GetNumberOfBlocks()):
        b = data.GetBlock(i)
        a = b.GetFieldData().GetArray("TimeValue") if b is not None else None
        if a is None:
            return []
        out.append(a.GetValue(0))
    return out


def frames(data):
    """The datasets of Data: each frame of a multiblock, else the one dataset."""
    if data is None:
        return []
    if data.IsA("vtkMultiBlockDataSet"):
        return [data.GetBlock(i) for i in range(data.GetNumberOfBlocks())]
    return [data]
