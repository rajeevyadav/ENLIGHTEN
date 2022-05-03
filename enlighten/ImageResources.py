import logging

from PySide2 import QtCore

log = logging.getLogger(__name__)

##
# This requires some explanation.  Device (model) images come from 
# enlighten/assets/uic_qrc/images/devices. However, they also have to be
# listed in devices.qrc.  They are then exposed through Qt through
# QtCore.QDirIterator.Subdirectories, which is iterated in this ctor.
#
# The final image is updated in EEPROMEditor.update_from_spec, using a pathname 
# generated by Spectrometer.get_image_pathname.
#
class ImageResources:

    def __init__(self):
        self.resources = []
        it = QtCore.QDirIterator(":", QtCore.QDirIterator.Subdirectories)
        while it.hasNext():
            self.resources.append(it.next())
        self.resources.sort()

    def contains(self, name):
        if name is None:
            return False
        return name in self.resources
