# Kernel module for Videology LVDS to MIPI adapter

Note: this module is valid only for Linux kernels > 5.12

[hardware description](https://videology-inc.atlassian.net/wiki/spaces/SUD/pages/65437727/SCAlLX-LVDS-2-MIPI)

================================================================================

#### To build and test device driver "lvds2mipi.ko" on Scailx device with ZoomBlock camera connected.

#### Follow steps as follows ...

#### `cd /usr/src/kernel`
#### `gunzip < /proc/config.gz > .config`
#### `make oldconfig`
#### `make prepare`
#### `make scripts`

#### 2. Check out this repository on Scailx camera.

#### 3. cd to local folder on camera, and build + install module.
####	`make` and `make modules_install`

#### 4. Check module is loaded `lsmod`.

#### 5. Check newly built module is in correct place.
####	'ls -lt /lib/modules/6*/updates*/lvds2mipi.ko`

#### 6.	Reboot Scailx and run `dmesg` to see new messages we added to the device driver C codes modprobe() function ;-)

#### 7. Test newly updated device driver with ZoomBlock camera and visca commands to check it works properly as expected.

================================================================================

Updates on python3 module ~/vdlg_lvds - Scailx Yocto bitbake module = python3-lvds2mipi.

2026.0520.	Updated go2rtc py program to use (camera name, id, device path) as combined string in 2 lists used by go2RTC and Portal.

2026.0327.	Added boson_stats.py and updated other py for more Boson camera formats including object and thermal detections for go2rtc.	

2026.0316.	Added py files to detect usb cameras live. Updated version to match Scailx Yocto 0.13.9. Built whl file in ~/dist and tested.


