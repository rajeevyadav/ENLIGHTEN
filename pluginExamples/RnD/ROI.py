import re
import os
import json
import numpy as np
import pandas as pd
import pexpect
import logging
import datetime
import traceback

from EnlightenPlugin import EnlightenPluginBase,    \
                            EnlightenPluginField,    \
                            EnlightenPluginResponse,  \
                            EnlightenPluginConfiguration

from wasatch.DetectorRegions import DetectorRegions
from wasatch.DetectorROI     import DetectorROI

log = logging.getLogger(__name__)

class ROI(EnlightenPluginBase):

    def __init__(self):
        super().__init__()

        self.pixel_mode = None
        self.detector_regions = DetectorRegions()

        self.clear()

    def get_configuration(self):
        fields = []

        fields.append(EnlightenPluginField(name="Region",        direction="input",  datatype=int,  initial=   0, minimum=0, maximum=   3, tooltip="Which ROI to configure"))
        fields.append(EnlightenPluginField(name="Y0",            direction="input",  datatype=int,  initial= 400, minimum=0, maximum=1079, tooltip="Start row"))
        fields.append(EnlightenPluginField(name="Y1",            direction="input",  datatype=int,  initial= 800, minimum=0, maximum=1079, tooltip="End row"))
        fields.append(EnlightenPluginField(name="X0",            direction="input",  datatype=int,  initial= 100, minimum=0, maximum=1951, tooltip="Start column"))
        fields.append(EnlightenPluginField(name="X1",            direction="input",  datatype=int,  initial=1200, minimum=0, maximum=1951, tooltip="End column"))
        fields.append(EnlightenPluginField(name="12-bit Data",   direction="input",  datatype=bool, initial=False, tooltip="12-bit pixel depth (vs 10-bit, default)"))
        fields.append(EnlightenPluginField(name="12-bit ADC",    direction="input",  datatype=bool, initial=False, tooltip="12-bit Analog-to-Digital Converter (vs 10-bit, default)"))
        fields.append(EnlightenPluginField(name="Pixel Mode",    direction="output", datatype=int,  initial=   0, tooltip="computed pixel mode"))
        fields.append(EnlightenPluginField(name="Save",          direction="input",  datatype="button", callback=self.save, tooltip="Save current trace"))
        fields.append(EnlightenPluginField(name="Clear",         direction="input",  datatype="button", callback=self.clear, tooltip="Clear traces"))

        return EnlightenPluginConfiguration(
            name = "Detector ROI", 
            has_other_graph = True,
            fields = fields,
            series_names = [ f"Region {x}" for x in range(4) ])

    def connect(self, enlighten_info):
        super().connect(enlighten_info)
        return True

    # At this point, unusually, we completely ignore the incoming ProcessedReading.
    # When multi-ROI is working, we may use this to split the unary spectrum into
    # multiple spectra.
    def process_request(self, request):
        pr = request.processed_reading 
        settings = request.settings
        wavelengths = settings.wavelengths

        if not settings.is_micro():
            return EnlightenPluginResponse(request, message = "Detector ROI requires SiG")

        region      = request.fields["Region"]
        y0          = request.fields["Y0"]
        y1          = request.fields["Y1"]
        x0          = request.fields["X0"]
        x1          = request.fields["X1"]
        adc_12      = request.fields["12-bit ADC"]
        depth_12    = request.fields["12-bit Data"]

        if not (y0 < y1 and x0 < x1) or (y0 == y1 == x0 == x1 == 0):
            return EnlightenPluginResponse(request, message = "invalid ROI")

        ########################################################################
        # Generate spectrometer commands
        ########################################################################

        cmds = []
        roi = DetectorROI(region, y0, y1, x0, x1)
        if not (self.detector_regions.has_region(region) and self.detector_regions.get_roi(region) == roi):
            cmds.append(("detector_roi", roi))
            self.detector_regions.add(roi)

        pixel_mode = (adc_12 << 1) | depth_12
        if self.pixel_mode is None or self.pixel_mode != pixel_mode:
            cmds.append(("pixel_mode", pixel_mode))
        self.pixel_mode = pixel_mode

        ########################################################################
        # Process Spectra
        ########################################################################

        log.debug("generating subspectra")
        self.last_spectra = {}

        # split subspectra
        series = {}
        proc_len = len(pr.processed) if pr.processed is not None else 0
        expected_len = self.detector_regions.total_pixels()
        if proc_len != expected_len:
            log.debug(f"can't split spectra (proc {proc_len} != expected {expected_len})")
        else:
            regions = self.detector_regions.get_region_list()
            subspectra = self.detector_regions.split(pr.processed)
            for i in range(len(regions)):
                roi = regions[i]
                roi_x = roi.crop(wavelengths)
                self.last_spectra[roi.region] = { "x": roi_x, "y": subspectra[i] }

                log.debug(f"roi_x has len {len(roi_x)} from {roi_x[0]} to {roi_x[-1]}")

                name = f"Region {i}"
                series[name] = self.last_spectra[roi.region]

        # cached traces
        for i in range(len(self.traces)):
            log.debug(f"appending trace {i}")
            series[f"Trace {i}"] = self.traces[i]

        return EnlightenPluginResponse(request, commands=cmds, series=series, outputs={ "Pixel Mode": pixel_mode })

    def save(self):
        log.debug("save button clicked")
        for key in self.last_spectra:
            log.debug(f"saving trace from region {key}")
            self.traces.append(self.last_spectra[key])

    def clear(self):
        log.debug("clearing traces")
        self.last_spectra = {}
        self.traces = []

    def report_error(self, msg):
        self.error_message = msg
        log.error(f"report_error: {msg}")
        return False
