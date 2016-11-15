# MyQ

Plugin for the Indigo Home Automation system.

This plugin communicates with the MyQ gateway.

The plugin auto-creates the Indigo devices after entering your MyQ login information. It was either do that, or cache the device information so users can pick specific openers to create devices for. Right now, it will always create devices for all openers that MyQ knows about.


### Indigo 7 Only

This plugin only works under Indigo 7 or greater.

This version now uses the Indigo 7 "Lock" device type.  So a closed door is "Locked" and anything else (open, moving, unknown) is "Unlocked".  I'd prefer an Open/Close semantic, but Indigo doesn't support that at this time.
