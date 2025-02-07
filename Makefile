################################################################################
#                                                                              #
#  Convenience Makefile for old fogies who can't imagine its lack.             #
#                                                                              #
################################################################################

.PHONY: docs doc

# by default, run indefinitely
RUN_SEC := 0

VERSION := $(shell grep 'VERSION =' enlighten/common.py | awk '{print $$3}' | tr -d '"')
RPI_ID := $(shell test -f /etc/os-release && grep '^ID=' /etc/os-release | awk -F= '{print $$2}' | tr -d '"')
RPI_CODENAME := $(shell test -f /etc/os-release && grep '^VERSION_CODENAME=' /etc/os-release | awk -F= '{print $$2}' | tr -d '"')

help:
	@echo "To build and run Enlighten, see README.md"
	@echo
	@echo "Supported targets:"
	@echo
	@echo "  run             - runs Enlighten from source"
	@echo
	@echo "  clean           - purge build artifacts (must re-run 'make deps')"
	@echo "  designer        - runs Qt Designer with main GUI"
	@echo "  deps            - rebuilds Qt artifacts after editing with Designer"
	@echo
	@echo "  cloc            - count SLOC in Python, JSON and .ini files"
	@echo "  doc             - render documentation"
	@echo "  linux-installer - build a Linux binary using pyinstaller"
	@echo "  rpi-installer   - build a Raspberry Pi binary using pyinstaller"
	@echo "  mac-installer   - build a Mac application using pyinstaller and platypus"
	@echo 
	@echo "VERSION = $(VERSION)"

cloc:
	@cloc --include-lang=Python,JSON,INI --exclude-dir=uic_qrc .

# You may need to do this if you're sharing a sandbox between Linux, Windows, Mac
# etc to force .pyc rebuilds
clean:
	@rm -rfv scripts/built-dist/Enlighten* \
             scripts/windows_installer/*.exe \
             scripts/work-path/Enlighten \
             enlighten/assets/uic_qrc/*.py \
             build \
             build-{linux,mac}* \
             ENLIGHTEN-*.app \
             ENLIGHTEN-linux-*.tgz \
             ENLIGHTEN-MacOS-*.zip \
             ENLIGHTEN-*.exe \
             mac.bundled \
             docs/doxygen \
             enlighten.{err,out} \
             doxygen.{err,out}
	@find . -name \*.pyc -exec rm -v {} \;
	@echo
	@echo "You may have to run 'scripts/rebuild_resources.sh' TWICE to get grey_icons_rc.py(?)"
	@echo

deps:
	@scripts/rebuild_resources.sh

designer:
	@./designer.sh

doc: docs

docs:
	@# Render Doxygen
	@#
	@echo Rendering Doxygen...
	@rm -rf docs/doxygen/html
	@test -L wasatch || ln -s ../Wasatch.PY/wasatch
	@doxygen 1>doxygen.out 2>doxygen.err
	@test -L wasatch && rm wasatch
	@#
	@# Convert Changelog to HTML
	@#
	@echo "<!-- This file is generated by enlighten/Makefile and uploaded by enlighten/scripts/deploy.  Do not hand-edit. -->" > docs/ENLIGHTEN_CHANGELOG.html
	@pandoc --metadata title:ENLIGHTEN-Changelog --toc --embed-resources --standalone --from gfm --to html README_CHANGELOG.md >> docs/ENLIGHTEN_CHANGELOG.html
	@#
	@# done
	@#
	@echo
	@echo "View via:" 
	@echo
	@echo "    firefox docs/doxygen/html/index.html"

# We don't seem to have to do this "EnlightenGUI" stuff on Windows, because the 
# executable is named enlighten.exe and doesn't conflict with the enlighten/ directory;
# we don't have to do it on Mac, because pyinstaller doesn't support bundles and
# we have to roll all that in via platypus externally.
linux-installer-base:
	rm -rf build-linux*
	mkdir -p build-linux
	pyinstaller \
        --distpath="build-linux" \
        --workpath="build-linux-work" \
        --noconfirm \
        --clean \
        --windowed \
        --paths="../Wasatch.PY" \
        --paths="pluginExamples" \
        --hidden-import="scipy._lib.messagestream" \
        --hidden-import="scipy.special.cython_special" \
        --icon "../enlighten/assets/uic_qrc/images/EnlightenIcon.ico" \
        --specpath="scripts" \
        --name EnlightenGUI \
        scripts/Enlighten.py 2>&1 \
        | sed 's/^/pyinstaller: /'
	mkdir -p                             build-linux/EnlightenGUI/enlighten/assets
	cp -rv enlighten/assets/stylesheets  build-linux/EnlightenGUI/enlighten/assets
	cp -rv enlighten/assets/example_data build-linux/EnlightenGUI/enlighten/assets
	cp -rv udev                          build-linux/EnlightenGUI/
	mv build-linux/EnlightenGUI build-linux/ENLIGHTEN-$(VERSION)
	( cd build-linux && tar zcvf ../ENLIGHTEN-linux-$(VERSION).tgz ENLIGHTEN-$(VERSION) | sed 's/^/compressing: /' )

linux-installer: linux-installer-base
	@echo 
	@echo "ENLIGHTEN-$(VERSION) for Linux packaged in ENLIGHTEN-linux-$(VERSION).tgz"

rpi-installer: linux-installer-base
	@echo 
	@FILENAME="ENLIGHTEN-${RPI_ID}-${RPI_CODENAME}-$(VERSION).tgz" && \
        mv ENLIGHTEN-linux-$(VERSION).tgz $$FILENAME && \
        echo "ENLIGHTEN-$(VERSION) for Raspberry Pi packaged in $$FILENAME"

mac-installer:
	@rm -rf build-mac build-mac-work
	@mkdir -p build-mac
	@echo "Running Pyinstaller..."
	@pyinstaller \
        --distpath="build-mac" \
        --workpath="build-mac-work" \
        --noconfirm \
        --clean \
        --windowed \
        --paths="../Wasatch.PY" \
        --paths="pluginExamples" \
        --hidden-import="scipy._lib.messagestream" \
        --hidden-import="scipy.special.cython_special" \
        --icon "../enlighten/assets/uic_qrc/images/EnlightenIcon.ico" \
        --specpath="scripts" \
        --name EnlightenGUI \
        scripts/Enlighten.py 2>&1 \
        | sed 's/^/pyinstaller: /'
	mkdir -p                             build-mac/EnlightenGUI/enlighten/assets
	cp -rv enlighten/assets/stylesheets  build-mac/EnlightenGUI/enlighten/assets
	cp -rv enlighten/assets/example_data build-mac/EnlightenGUI/enlighten/assets
	@$(MAKE) mac-platypus

# install with "brew install platypus"
mac-platypus:
	@echo "Running Platypus..."
	@rm -rf ENLIGHTEN-$(VERSION).app
	@DIR=build-mac/EnlightenGUI ; ls $$DIR | grep -v EnlightenGUI | sed "s!^!-f $$DIR/!" > mac.bundled
	@platypus \
        --name "ENLIGHTEN™ $(VERSION)" \
        --interface-type 'None' \
        --interpreter /usr/bin/env \
        --app-icon enlighten/assets/uic_qrc/images/EnlightenIcon.icns \
        --app-version $(VERSION) \
        --author "Wasatch Photonics" \
        --bundle-identifier "com.wasatchphotonics.Enlighten" \
        --quit-after-execution \
        --overwrite \
        --optimize-nib \
        `cat mac.bundled` \
        build-mac/EnlightenGUI/EnlightenGUI \
        ENLIGHTEN-$(VERSION) 2>&1 \
        | sed 's/^/platypus: /'
	@zip -r ENLIGHTEN-MacOS-$(VERSION).zip ENLIGHTEN-$(VERSION).app | sed 's/^/compressing: /'
	@rm -rf ENLIGHTEN-$(VERSION).app
	@echo 
	@echo "ENLIGHTEN-$(VERSION).app for MacOS packaged in ENLIGHTEN-MacOS-$(VERSION).zip"

# Run ENLIGHTEN with debug logging (obey time constraint if given)
run:
	@(python -u scripts/Enlighten.py --log-level debug --run-sec $(RUN_SEC) 1>enlighten.out 2>enlighten.err && cat enlighten.err) || cat enlighten.err

# Run ENLIGHTEN with logging disabled (standard release conditions)
run-release:
	@(python -u scripts/Enlighten.py --run-sec $(RUN_SEC) 1>enlighten.out 2>enlighten.err && cat enlighten.err) || cat enlighten.err

# Run ENLIGHTEN until memory growth exceeds 20% of start
run-20-perc:
	@(python -u scripts/Enlighten.py --max-memory-growth 20 --log-level debug 1>enlighten.out 2>enlighten.err && cat enlighten.err) || cat enlighten.err
