[app]

# Kimi K2.6 UDE - Android App
title = Kimi K2.6 UDE
package.name = kimiude
package.domain = org.kimi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,env
version = 1.0.0
requirements = python3,kivy,pillow,requests
# Android permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
# Android entry point
android.entrypoint = main_android.py
# App orientation
orientation = portrait
# Android API levels
android.api = 33
android.minapi = 21
android.ndk = 25b
# Android architecture (arm64 only for faster build)
android.archs = arm64-v8a
# Buildozer-specific
fullscreen = 0
android.allow_backup = True
# Icon and presplash
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
# Logging
log_level = 2
# Presplash color
presplash.color = #0F1117
# p4a branch for building
p4a.branch = master
# Accept SDK licenses
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
