[app]

# Kimi K2.6 UDE - Android App
title = Kimi K2.6 UDE
package.name = kimiude
package.domain = org.kimi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,env
version = 1.1.0
requirements = python3==3.11.9,kivy==2.3.0,pillow==10.4.0,requests
# Android permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
# Android entry point - must be main.py for p4a
android.entrypoint = main.py
# App orientation
orientation = portrait
# Android API levels - lower target for broader compatibility
android.api = 31
android.minapi = 21
android.ndk = 25b
# Android architecture - BOTH architectures for all devices
android.archs = armeabi-v7a,arm64-v8a
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
# p4a - use specific tag for stable recipe versions
p4a.branch = v2024.01.21
# Accept SDK licenses
android.accept_sdk_license = True
# Ensure proper debug signing
android.debug_release = True
# Grant runtime permissions automatically
android.auto_backup = False
# Manifest additions for installability
android.manifests = a=android:extractNativeLibs\=true

[buildozer]
log_level = 2
warn_on_root = 1
