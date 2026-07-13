from PyInstaller.utils.hooks import collect_all, collect_submodules


datas = []
binaries = []
hiddenimports = []

for package in ("mcp", "sqlglot", "pydantic", "pydantic_settings"):
    module_filter = lambda name: True
    if package == "mcp":
        module_filter = lambda name: not name.startswith("mcp.cli")
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package, filter_submodules=module_filter
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports += collect_submodules("anyio")
hiddenimports = [name for name in hiddenimports if not name.startswith("mcp.cli")]

a = Analysis(
    ["scripts/archery_mcp_entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["mcp.cli", "pytest", "pytest_asyncio", "typer"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="archery-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
