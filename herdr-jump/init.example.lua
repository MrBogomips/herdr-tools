-- ~/.hammerspoon/init.lua with HerdrJump. Link the Spoon first (see README.md).

hs.uploadCrashData(false) -- no crash reports sent to Hammerspoon's crash collector
hs.autoLaunch(true) -- start Hammerspoon at login
hs.dockIcon(false) -- menu bar only
require("hs.ipc") -- optional: the `hs` command line, handy for checks

hs.loadSpoon("HerdrJump")
spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)
spoon.HerdrJump:start()
