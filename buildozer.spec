[app]

# Kimi K2.6 UDE - Android App
title = Kimi K2.6 UDE
package.name = kimiude
package.domain = org.kimi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,env
version = 1.0.0
requirements = python3==3.11.9,kivy==2.3.0,pillow,requests
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
android.sdk = 33
# Android architecture
android.archs = arm64-v8a, armeabi-v7a
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
# Android gradle dependencies
android.gradle_dependencies = 
# Window size for desktop testing
[buildozer]
log_level = 2
warn_on_root = 1
