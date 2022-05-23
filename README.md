# MyQ

Plugin for the Indigo Home Automation system.

This plugin communicates with the MyQ gateway.

| Requirement            |                     |   |
|------------------------|---------------------|---|
| Minimum Indigo Version | 2022.1              |   |
| Python Library (API)   | Unsupported         |   |
| Requires Local Network | No                  |   |
| Requires Internet      | Yes                 |   |
| Hardware Interface     | None                |   |

The plugin auto-creates the Indigo devices after entering your MyQ login information. It was either do that, 
or cache the device information so users can pick specific openers to create devices for. Right now, it will 
always create devices for all openers that MyQ knows about.

This plugin uses the Indigo "Lock" device type.  So a closed door is "Locked" and anything else (open, moving, unknown) is "Unlocked".  I'd prefer an Open/Close semantic, but Indigo doesn't support that at this time.

**PluginID**: com.flyingdiver.indigoplugin.myq

## Installation Instructions

Before installing the plugin - in Terminal.app enter:

`pip3 install pymyq==3.1.5`
