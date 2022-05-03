import logging

from . import util

# Dialog box cruft
from PySide2 import QtGui, QtCore 
from .assets.uic_qrc import dialog_advanced_options
from .BasicDialog import BasicDialog

log = logging.getLogger(__name__)

##
# Encapsulates the "Advanced Options" control widget atop the Spectrometer 
# Control column on the GUI.
#
# - persists state ("never_show") through Configuration / enlighten.ini
# - is potentially affected by selected / current spectrometer or hotplugs (not 
#   all models support TEC control or AreaScan)
#
# @par Relationship to Authentication
#
# Currently there is no interaction betwween Authentication (which "hides" 
# non-user-facing features like rare OEM and Manufacturing options behind
# passwords) and Advanced Options (which simply hides them behind a warning 
# dialog).
#
# Checking the Advanced Options checkbox does not affect your "login level"
# with respect to Authentication, nor does logging-in affect your Advanced 
# Options selection(s).  They are different "gateways" which obscure / protect
# different sets of features.
#
class AdvancedOptionsFeature:
    
    def __init__(self,
            cb_enable,          # main "enable" checkbox for Advanced Features
            cb_area_scan,       # whether to show AreaScan widget
            cb_baseline,        # whether to show BaselineCorrection widget
            cb_post,            # whether to show PostProcessingOptions widget
            cb_region,          
            cb_tec,             # whether to show TECControl widget
            config,             # Configuration (enlighten.ini)
            fr_subopt,          # sub-frame wrapping all CheckBoxes other than Enable
            fr_area_scan,       # frame containing AreaScan widget
            fr_baseline,        # frame containing BaselineCorrection widget
            fr_post,            # frame containing PostProcessingOptions widget
            fr_region,
            fr_tec,             # frame containing TECControl widget
            multispec,          # used to selectively "allow" use of model-specific features on hotplug / selection
            stylesheets):       # used to format dialog

        self.cb_enable      = cb_enable
        self.cb_area_scan   = cb_area_scan
        self.cb_baseline    = cb_baseline
        self.cb_post        = cb_post
        self.cb_region      = cb_region
        self.cb_tec         = cb_tec
        self.config         = config
        self.fr_subopt      = fr_subopt
        self.fr_area_scan   = fr_area_scan
        self.fr_baseline    = fr_baseline
        self.fr_post        = fr_post
        self.fr_region      = fr_region
        self.fr_tec         = fr_tec
        self.multispec      = multispec

        self.enabled            = False
        self.area_scan_visible  = False
        self.baseline_visible   = False
        self.post_visible       = False
        self.region_visible     = False
        self.tec_visible        = False

        self.dialog_shown       = False
        self.dialog_warning     = BasicDialog(title="Advanced Options Confirmation", layout=dialog_advanced_options, modal=True)
        self.never_show         = self.config.get_bool("advanced_options", "never_show")

        stylesheets.apply(self.dialog_warning, "enlighten") 

        self.cb_enable                      .stateChanged   .connect(self.enable_callback)
        self.cb_area_scan                   .stateChanged   .connect(self.area_scan_callback)
        self.cb_baseline                    .stateChanged   .connect(self.baseline_callback)
        self.cb_post                        .stateChanged   .connect(self.post_callback)
        self.cb_region                      .stateChanged   .connect(self.region_callback)
        self.cb_tec                         .stateChanged   .connect(self.tec_callback)
        self.dialog_warning.ui.buttonBox    .accepted       .connect(self.dialog_accepted_callback)
        self.dialog_warning.ui.buttonBox    .rejected       .connect(self.dialog_rejected_callback)

        self.update_visibility()

    # ##########################################################################
    #                                                                          #
    #                             Public Methods                               #
    #                                                                          #
    # ##########################################################################

    def update_visibility(self):
        log.debug("AdvancedOptionsFeature: update_visibility")
        spec = self.multispec.current_spectrometer()
        if spec is None:
            log.debug("AdvancedOptionsFeature: update_visibility (no spec)")
            self.enabled = False

            self.fr_subopt      .setVisible(False)
            self.fr_area_scan   .setVisible(False)
            self.fr_baseline    .setVisible(False)
            self.fr_post        .setVisible(False)
            self.fr_region      .setVisible(False)
            self.fr_tec         .setVisible(False)
            self.cb_enable      .setChecked(False)
            self.cb_area_scan   .setChecked(False)
            self.cb_baseline    .setChecked(False)
            self.cb_post        .setChecked(False)
            self.cb_region      .setChecked(False)
            self.cb_tec         .setChecked(False)

            self.set_area_scan_available(False)
            self.set_tec_available(False)
            self.set_region_available(False)
            return
    
        is_ingaas = spec.settings.is_ingaas()
        log.info("AdvancedOptionsFeature: is_ingaas %s", is_ingaas)

        self.enabled = self.cb_enable.isChecked()
        
        self.set_area_scan_available(not is_ingaas)
        self.set_tec_available(spec.settings.eeprom.has_cooling)
        self.set_region_available(spec.settings.is_imx())

        self.fr_subopt      .setVisible(self.enabled)
        self.fr_area_scan   .setVisible(self.area_scan_visible)
        self.fr_baseline    .setVisible(self.baseline_visible)
        self.fr_post        .setVisible(self.post_visible)
        self.fr_region      .setVisible(self.region_visible)
        self.fr_tec         .setVisible(self.tec_visible)

    # ##########################################################################
    #                                                                          #
    #                           Dialog Shenanigans                             #
    #                                                                          #
    # ##########################################################################

    ## The user clicked "Cancel" on the warning dialog 
    def dialog_rejected_callback(self):
        self.cb_enable.setChecked(False)
        self.update_gui()

    ## The user clicked "Ok" on the warning dialog (and maybe the checkbox).
    def dialog_accepted_callback(self):
        self.dialog_shown = True
        self.never_show = self.dialog_warning.ui.checkBox.isChecked()
        self.config.set("advanced_options", "never_show", self.never_show)
        self.update_gui()

    ## The user clicked the "Advanced" checkbox, so display or hide the sub-options frame
    def enable_callback(self):
        if self.cb_enable.isChecked() and not self.dialog_shown and not self.never_show:
            return self.dialog_warning.display()
        self.update_gui()
    
    def update_gui(self):
        self.enabled = self.cb_enable.isChecked()
        self.fr_subopt.setVisible(self.enabled)
        if not self.enabled:
            self.cb_area_scan.setChecked(False)
            self.cb_baseline .setChecked(False)
            self.cb_post     .setChecked(False)
            self.cb_region   .setChecked(False)
            self.cb_tec      .setChecked(False)

    # ##########################################################################
    #                                                                          #
    #                         Availability Methods                             #
    #                                                                          #
    # ##########################################################################

    # These methods are used to optionally hide or make available options which
    # only apply to certain types of spectrometer (TEC, area scan etc)

    ## 
    # It has been decided that TEC Control is (or is not) a reasonable option for
    # the current spectrometer
    def set_tec_available(self, flag):
        self.cb_tec.setVisible(flag)
        if not flag:
            self.tec_visible = False
            self.fr_tec.setVisible(False)

    ## 
    # It has been decided that Area Scan is (or is not) a reasonable option for 
    # the current spectrometer
    def set_area_scan_available(self, flag):
        self.cb_area_scan.setVisible(flag)
        if not flag:
            self.area_scan_visible = False
            self.fr_area_scan.setVisible(False)

    def set_region_available(self, flag):
        self.cb_region.setVisible(flag)
        if not flag:
            self.region_visible = False
            self.fr_region.setVisible(False)

    # ##########################################################################
    #                                                                          #
    #                         Per-Feature Callbacks                            #
    #                                                                          #
    # ##########################################################################

    # the per-feature checkbox callbacks

    def area_scan_callback(self):
        self.area_scan_visible = self.cb_area_scan.isChecked()
        self.fr_area_scan.setVisible(self.area_scan_visible)

    def baseline_callback(self):
        self.baseline_visible = self.cb_baseline.isChecked()
        self.fr_baseline.setVisible(self.baseline_visible)

    def post_callback(self):
        self.post_visible = self.cb_post.isChecked()
        self.fr_post.setVisible(self.post_visible)

    def region_callback(self):
        self.region_visible = self.cb_region.isChecked()
        self.fr_region.setVisible(self.region_visible)

    def tec_callback(self):
        self.tec_visible = self.cb_tec.isChecked()
        self.fr_tec.setVisible(self.tec_visible)