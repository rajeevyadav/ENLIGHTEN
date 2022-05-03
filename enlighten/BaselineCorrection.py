import copy
import numpy as np
import logging

from superman.baseline import BL_CLASSES, AirPLS
from .ScrollStealFilter import ScrollStealFilter

from wasatch import utils as wasatch_utils

log = logging.getLogger(__name__)

##
# Encapsulates baseline correction.
#
# We've always needed to add proper background subtraction. This need has been
# highlighted by the observed importance of proper baseline correction 
# (fluorescence subtraction) to get good results in KnowItAll.
#
# @par Visibility / Usability
#
# There are two paths to BaselineCorrection: 
#
# - implicit operation: automatically enabled, with default algo (AirPLS), when in
#   Raman Mode, but ONLY if a horizontally vignetted ROI is configured.
#
# - explicit operation: if user checked "Advanced Options" then "Baseline Correction"
#   in the "Advanced Options" widget, then manually clicked "Enabled" in the Baseline
#   Correction widget.
# 
# @par ModPoly
#
# Dieter reports that ModPoly (or IModPoly), based on Lieber & Mahadevan-Jansen 
# (2003), is pretty much the industry standard and what he typically uses from R
# via baseline.modpolyfit().
#
# @par PyHAT (USGS)
#
# It looks like there's already an open-source ModPoly Python implementation here:
#
# - https://github.com/USGS-Astrogeology/PyHAT/blob/dev/libpyhat/transform/baseline_code/polyfit.py
#
# I tried installing the entire PyHAT module via conda (both conda-forge and 
# usgs-astrogeology channels), also via pip and "python setup.py install", but the
# various dependencies don't seem to coincide on Win32 under Python 3.7. 
# 
# Specifically, they don't even seem to support PyHAT on Windows at all, although 
# the related plio is available:
# 
# - https://anaconda.org/usgs-astrogeology/pyhat
# - https://anaconda.org/usgs-astrogeology/plio
# 
# @par Superman
# 
# It looks like the open-source [Superman](https://github.com/all-umass/superman)
# module has a working ModPoly (PolyFit), and several other algorithms as well. 
# I wasn't able to get Mario working, and Wavelet had an unmet dependency (fixed),
# but most are now exposed by ENLIGHTEN.
#
# I made a couple tweaks to the WasatchPhotonics fork of Superman, which allow it
# to build with Visual Studio Community 2019, and expose an extra parameter
# in the AirPLS constructor (whittaker).  Sadly, while my local build works fine
# in my development environment, it blows up when run after pyinstaller.  There
# is probably some DLL I need to bundle, or a "hidden import" I need to capture,
# but the truth is I only needed that to access the Whittaker param and I don't
# think it's that essential, so for now it's back to the pip distro.
# 
# @par References
#
# - https://link.springer.com/content/pdf/10.1007%2Fs13320-018-0512-y.pdf
# - https://arxiv.org/ftp/arxiv/papers/1306/1306.4156.pdf 
#
class BaselineCorrection:

    DEFAULT_ALGO_NAME = "AirPLS"
    
    ## @todo add cb_zero
    def __init__(self,
            cb_enabled,         # whether we're actively correcting the baseline
            cb_show_curve,      # whether we should show the computed baseline (whether it's being subtracted or not)
            combo_algo,
            config,
            generate_x_axis,
            guide,
            multispec,
            page_nav,
            vignette_roi,
            graph):

        self.cb_enabled      = cb_enabled
        self.cb_show_curve   = cb_show_curve
        self.combo_algo      = combo_algo
        self.config          = config
        self.generate_x_axis = generate_x_axis
        self.guide           = guide
        self.multispec       = multispec
        self.page_nav        = page_nav
        self.vignette_roi    = vignette_roi

        self.current_algo_name = BaselineCorrection.DEFAULT_ALGO_NAME
        self.enabled = False
        self.allowed = False
        self.show_curve = False
        self.advanced_options = None

        # per Dieter 2020-05-22
        self.airpls_smoothness_param = 20
        self.airpls_max_iters = 500
        self.airpls_conv_thresh = 8e-4
        self.airpls_whittaker_deriv_order = 2

        # first check whether one should be selected and/or enabled
        self.init_from_config()

        # now get the list, create the objects and populate the combobox
        self.init_algos()

        # now create bindings
        self.cb_enabled     .stateChanged       .connect(self.update_visibility)
        self.cb_show_curve  .stateChanged       .connect(self.update_visibility)
        self.combo_algo     .currentIndexChanged.connect(self.update_visibility)
        self.combo_algo                         .installEventFilter(ScrollStealFilter(self.combo_algo))

        # now that bindings are connected, select the default/previous algo in 
        # the combobox and optionally enable
        self.reset(enable=self.enabled)

        # just in case that didn't trigger a change
        self.update_visibility()

        # we need to know when Vignetting is turned on/off
        self.vignette_roi.register_observer(self.update_visibility)

        self.curve = graph.add_curve("baseline", rehide=False, in_legend=False)
        self.curve.setVisible(False)

    ##
    # This will overwrite the default algo name, if provided
    #
    # [Auto-enabling at launch] requires thought.  We want to enable process-mode
    # applications to automatically start-up with baseline correction applied, if
    # that is part of their logic, but we really don't want "normal" desktop users
    # starting with baseline correction pre-enabled -- it causes too much 
    # confusion, especially with darks.  
    #
    # Ultimately I replaced:
    #   - config("baseline_correction", "enabled") 
    #   + config("batch_collection", "baseline_correction_enabled")
    #
    def init_from_config(self):
        s = "baseline_correction"

        def set(field, value):
            if value is None:
                return
            log.debug("%s -> %s", field, value)
            setattr(self, field, value)

        # if self.config.has_option(s, "algo"):
        #     self.current_algo_name = self.config.get(s, "algo")

        # AirPLS options for Dieter
        set("current_algo_name",            self.config.get      (s, "algo",                         default=None))
        set("airpls_max_iters",             self.config.get_int  (s, "airpls_max_iters",             default=None))
        set("airpls_smoothness_param",      self.config.get_int  (s, "airpls_smoothness_param",      default=None))
        set("airpls_whittaker_deriv_order", self.config.get_int  (s, "airpls_whittaker_deriv_order", default=None))
        set("airpls_conv_thresh",           self.config.get_float(s, "airpls_conv_thresh",           default=None))

    ## 
    # Populate the combobox from the hardcoded list of supported algos 
    # (instantiating each as we go).
    #
    # @note 'mario' didn't work
    # @note this is called before bindings, so no callbacks will be issued
    def init_algos(self):
        names = { 
          # ComboBox label       Superman class
            'AirPLS':            'airpls',
            'ALS':               'als',
            'Dietrich':          'dietrich',
            'FABC':              'fabc',
            'Kajfosz-Kwiatek':   'kk',
            'MedianFilter':      'median',
            'MPLS':              'mpls',
            'PolyFit':           'polyfit',
            'Rubberband':        'rubberband',
            'Tophat':            'tophat',
            'Wavelet':           'wavelet' }
        self.combo_algo.clear()
        self.algos = {}

        # iterate through names in case-insensitive dictionary order (so capitalized ALS doesn't preceed AirPLS)
        for (name, abbr) in sorted(names.items(), key=lambda t: t[0].lower()): 
            self.combo_algo.addItem(name)
            try:
                # allow customization of parameters
                if name == "AirPLS":
                    # per Dieter 2-Mar-20, lambda of 200-250 seems optimal for WP-785-SR
                    algo = AirPLS(smoothness_param      = self.airpls_smoothness_param,
                                  max_iters             = self.airpls_max_iters,
                                  conv_thresh           = self.airpls_conv_thresh)
                                 #whittaker_deriv_order = self.airpls_whittaker_deriv_order)
                else:
                    algo = BL_CLASSES[abbr]()
                self.algos[name] = algo
            except:
                log.error("failed to instantiate BaselineCorrection algo %s (%s)", name, abbr, exc_info=1)
                self.algos[name] = None

    ##
    # Called by Controller on first visit to Raman mode, per Dieter.  
    #
    # This selects the default (or last-used) algo in the combobox, then 
    # optionally enables the feature.
    #
    # @param enable (Input) if true, enable the feature (does NOT disable on false!)
    def reset(self, enable=False):
        log.debug("reset(enable=%s)", enable)
        for index in range(self.combo_algo.count()):
            label = self.combo_algo.itemText(index) 
            if label == self.current_algo_name:
                self.combo_algo.setCurrentIndex(index)

        if enable and self.current_algo_name is not None:
            self.cb_enabled.setChecked(True)

    def update_visibility(self):
        allowed = False
        # implicit operation allowed if RAMAN with VIGNETTING
        if self.page_nav.doing_raman():
            allowed = True

        # explicit operation through Advanced Options
        if self.advanced_options is not None:
            if self.advanced_options.baseline_visible:
                allowed = True

        spec = self.multispec.current_spectrometer()

        # store in object (used by KIA)
        self.allowed = allowed

        if not self.allowed:
            self.enabled = False
            self.show_curve = False
            self.algo = None
            if spec is not None:
                spec.app_state.baseline_correction_enabled = self.enabled
            return

        # apparently we're in a technique and spectrometer that supports baseline
        # correction (or we've been overridden by Advanced Options)

        name = self.combo_algo.currentText()
        try:
            if name is not None:
                self.algo = self.algos[name]
                self.current_algo_name = name
                self.config.set("baseline_correction", "algo", name)
        except:
            self.algo = None
            self.current_algo_name = None
            log.error("unknown algo %s", name)
            return

        self.enabled = self.cb_enabled.isChecked()
        if spec is not None:
            spec.app_state.baseline_correction_enabled = self.enabled

        self.show_curve = self.cb_show_curve.isChecked()
        self.curve.setVisible(self.show_curve)

        if self.enabled:
            self.guide.clear(token="enable_baseline_correction")

    ##
    # @param pr   (In/Out) ProcessedReading
    # @param spec (Input)  Spectrometer
    #
    # @note uses vignetted spectrum if found
    def process(self, pr, spec):
        # log.debug("process: show_curve %s, enabled %s, algo %s, pr %s", self.show_curve, self.enabled, self.algo, pr)

        if spec is None:
            return

        # default to no correction applied
        spec.app_state.baseline_correction_algo = None

        # if we're neither displaying nor subtracting the baseline, don't bother
        if not (self.show_curve or self.enabled):
            return

        if pr is None or pr.processed is None or len(pr.processed) < 2 or self.algo is None:
            return

        spectrum = pr.get_processed()
        x_axis = self.generate_x_axis(spec=spec, vignetted=pr.is_cropped())

        baseline = self.generate_baseline(spectrum=spectrum, x_axis=x_axis)
        if baseline is None:
            log.error("unable to generate baseline")
            return 

        # generate the baseline and optionally display it, even if we're not 
        # enabled and therefore not applying the corrected baseline
        if self.show_curve and self.multispec.is_current_spectrometer(spec):
            # log.debug("showing baseline: %s", baseline)
            self.curve.setData(y=baseline, x=x_axis)

        if not self.enabled:
            # log.debug("not enabled, so returning unmodified spectrum")
            return

        spec.app_state.baseline_correction_algo = self.current_algo_name

        # log.debug("subtracting baseline of %d pixels", len(baseline))
        corrected = np.subtract(spectrum, baseline)
        corrected[corrected < 0] = 0

        pr.set_processed(corrected)

    def generate_baseline(self, spectrum, x_axis):
        # log.debug("generating baseline with %s", self.current_algo_name)
        intensities = np.array(spectrum, dtype=np.float64)
        bands       = np.array(x_axis, dtype=np.float64)

        try:
            fitted = self.algo.fit(
                bands       = bands, 
                intensities = intensities, 
                segment     = False,              # doesn't seem to matter?
                invert      = False)

            baseline = np.clip(fitted.baseline, -65535, 65535)
            return baseline
        except:
            log.error("exception in baseline_correction.generate_baseline with algo %s", self.current_algo_name, exc_info=1)
