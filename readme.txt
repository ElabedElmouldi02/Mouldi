Intel(R) Network Connections Software, Release 30.4
***************************************************

August 21, 2025

This release includes software and drivers for Intel(R) Ethernet
adapters and integrated network connections.


Contents
^^^^^^^^

* Intel(R) Network Connections Software, Release 30.4

  * What's New in This Release

  * User Guides

  * Bug Fixes and Known Issues

  * Supported Operating Systems

  * Supported Hardware

  * Intel Fiber Optic Connections

  * Customer Support

  * Legal / Disclaimers


What's New in This Release
==========================

See the release notes for a full listing of new or removed features in
this release. To view the release notes:

1. Go to the following page on intel.com:

   https://www.intel.com/content/www/us/en/content-details/778690
   /intel-ethernet-controller-products-release-notes.html?wapkw=Intel
   %C2%AE%20Ethernet%20Controller%20Products%20Release%20Notes&DocID=
   778690

2. In the list of results, click on the link for "Intel(R) Ethernet
   Controller Products Release Notes."

   * By default, the page lists the newest released version.

   * If you need to view the release notes for a different version,
     click on the "More Versions" link in the right side of the search
     result and select your desired version.


User Guides
===========

See the Intel(R) Ethernet Adapters and Devices User Guide for
installation instructions, explanations of supported features and
tools, and troubleshooting tips.

You can view this user guide in the Intel Resource and Documentation
Center at https://cdrdv2.intel.com/v1/dl/getContent/705831.

Note:

  Point releases (for example, 29.1.1) may not have a corresponding
  user guide version. In those cases, refer to the user guide for the
  major release (for example, 29.1).

If you need localized installation instructions, you can access them
at the following location within the software release:

   /DOCS/QUICK/quick.htm


Bug Fixes and Known Issues
==========================

See the release notes for the list of all currently known issues,
limitations, and resolved issues.


Supported Operating Systems
===========================

The drivers in this software release have been tested with the
operating systems (OSs) listed below. Additional OSs may function with
our drivers but are not tested.

Note:

  Not all devices support all operating systems listed. Refer to the
  Release Notes for detailed OS support information for your device.


Microsoft Windows Server, Azure Stack HCI, and Windows
------------------------------------------------------

* Microsoft Windows Server 2025

* Microsoft Windows Server 2022

* Microsoft Windows Server 2019, Version 1903

* Microsoft Windows Server 2016

* Microsoft Azure Stack HCI

* Microsoft Windows 11 version 24H2

* Microsoft Windows 11 version 23H2 (build 22631.2506)

* Microsoft Windows 11 version 22H2 (build 22621)

* Microsoft Windows 10 version 21H2 (build 19044)

* Microsoft Windows 10 RS5, Version 1809 (build 17763)

Note:

  * Devices based on the following do not support Microsoft Windows or
    Windows Server:

    * Intel® Ethernet Connection E822-C

    * Intel® Ethernet Connection E822-L

  * Some older Intel Ethernet adapters do not have full software
    support for the most recent versions of Microsoft Windows. Many
    older Intel Ethernet adapters have base drivers supplied by
    Microsoft Windows.

  * RDMA support is available on Microsoft Windows 10 version 21H2 and
    Microsoft Windows 11.

  * In Microsoft Windows Server 2025, all devices based on the Intel
    Ethernet 710 Series are reported with generic, 2-part device IDs
    and branding strings, and will be configured as generic devices
    with no custom default settings. This change resolves an issue
    seen when deploying network intent roles using the Network ATC
    scripts in Windows Server 2025 and Azure Stack HCI.

  * The HPE Synergy 4610C 10/25Gb Ethernet Adapter and HPE 10/25Gb
    Ethernet Adapter are not supported on Microsoft Windows Server
    2025.


VMware ESXi
-----------

* VMware ESXi 9.0

* VMware ESXi 8.0

* VMware ESXi 7.0

Please refer to VMware's download site for the latest ESXi drivers for
Intel Ethernet devices.


Linux
-----

* Linux Real Time Kernel 5.x and 4.x [1]

* Linux, v2.4 kernel or higher

* Red Hat Enterprise Linux (RHEL) 9.5

* Red Hat Enterprise Linux (RHEL) 9.6

* Red Hat Enterprise Linux (RHEL) 10.0

* SUSE Linux Enterprise Server (SLES) 15 SP6

* SUSE Linux Enterprise Server (SLES) 15 SP7

* SUSE Linux Enterprise Server 12 SP5

* Canonical Ubuntu 24.04 LTS

* Canonical Ubuntu 22.04 LTS

* Debian 11

* openEuler 22.03 LTS SP3 for AArch64 [2]

* Kylin Linux Advanced Server V10 - ARM [3]

* Linux Ubuntu 24.04 - ARM [4]

* Linux Ubuntu 24.04 - ARM - Real Time [4]

[1] Only supported on Intel® Ethernet E810 Series.

[2] Only supported on Intel® Ethernet E810 Series, with the Linux ice
    and iavf drivers and select Intel® Network Connection Tools. See
    tool readmes for details.

[3] Support is provided for the following components: ICE driver, iAVF
    driver, Bootutil, NVMUpdate, EPCT, EEUpdate, and CELO.

[4] Support is provided for the following components: ICE driver, iAVF
    driver, Bootutil, NVMUpdate, EPCT, LANConf (NDA only), EEUpdate,
    and CELO.


FreeBSD
-------

* FreeBSD 14.3

* FreeBSD 13.5


Supported Hardware
==================

This software release supports Intel® Ethernet devices based on the
silicon controllers and connections listed below.

For help identifying your network device and finding supported
devices, visit https://www.intel.com/support.

Note:

  Available features and settings are dependent on your device and
  operating system. **Not all settings are available on every
  device/OS combination.**


Intel® Ethernet 800 Series
--------------------------

* Intel® Ethernet Controller E810-C

* Intel® Ethernet Controller E810-XXV

* Intel® Ethernet Controller E830-CC

* Intel® Ethernet Controller E830-XXV

* Intel® Ethernet Network Adapter E830-C-Q2

* Intel® Ethernet Network Adapter E830-XXV-8F

* Intel® Ethernet Network Adapter E830-XXV-2

* Intel® Ethernet Connection E822-C

* Intel® Ethernet Connection E822-L

* Intel® Ethernet Connection E823-C

* Intel® Ethernet Connection E823-L

* Intel® Ethernet Connection E825-C


Intel® Ethernet 700 Series
--------------------------

* Intel® Ethernet Controller I710

* Intel® Ethernet Controller X710

* Intel® Ethernet Controller XL710

* Intel® Ethernet Network Connection X722

* Intel® Ethernet Controller XXV710

* Intel® Ethernet Controller V710


Intel® Ethernet 600 Series
--------------------------

* Intel® Ethernet Controller E610


Intel® Ethernet 500 Series
--------------------------

* Intel® Ethernet Controller 82599

* Intel® Ethernet Controller X520

* Intel® Ethernet Controller X550

* Intel® Ethernet Controller X552

* Intel® Ethernet Controller X553


Intel® Ethernet 300 Series and Other
------------------------------------

* Intel® I210 Gigabit Ethernet Controller

* Intel® I350 Gigabit Ethernet Controller

* Intel® Ethernet Controller I225

* Intel® Ethernet Controller I226

* Intel® Ethernet Connection I217

* Intel® Ethernet Connection I218

* Intel® Ethernet Connection I219


Intel Fiber Optic Connections
=============================

Caution: The fiber optic ports may utilize Class 1 or Class 1M laser
devices. Do not stare into the end of a fiber optic connector
connected to a "live" system. Do not use optical instruments to view
the laser output. Using optical instruments increases eye hazard.
Laser radiation is hazardous and may cause eye injury. To inspect a
connector, receptacle or adapter end, be sure that the fiber optic
device or system is turned off, or the fiber cable is disconnected
from the "live" system.

The Intel Gigabit and 10GbE network adapters with fiber optic
connections operate only at their native speed and only at full-
duplex. Therefore you do not need to make any adjustments. Use of
controls or adjustments or performance of procedures other than those
specified herein may result in hazardous radiation exposure. The laser
module contains no serviceable parts.


Customer Support
================

* Main Intel support website: https://support.intel.com

* Support for Intel Ethernet products:
  https://www.intel.com/content/www/us/en/support/products/36773
  /ethernet-products.html


Legal / Disclaimers
===================

Copyright (C) 2002 - 2025, Intel Corporation. All rights reserved.

Intel technologies may require enabled hardware, software or service
activation.

No product or component can be absolutely secure.

Your costs and results may vary.

Intel, the Intel logo, and other Intel marks are trademarks of Intel
Corporation or its subsidiaries.  Other names and brands may be
claimed as the property of others.

Performance varies by use, configuration, and other factors. Learn
more at https://www.Intel.com/PerformanceIndex.

The products described may contain design defects or errors known as
errata which may cause the product to deviate from published
specifications. Current characterized errata are available on request.

This software and the related documents are Intel copyrighted
materials, and your use of them is governed by the express license
under which they were provided to you ("License"). Unless the License
provides otherwise, you may not use, modify, copy, publish,
distribute, disclose or transmit this software or the related
documents without Intel's prior written permission.

This software and the related documents are provided as is, with no
express or implied warranties, other than those that are expressly
stated in the License.
