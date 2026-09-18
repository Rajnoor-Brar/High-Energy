# YODA via `yoda-config` (09 §1). Defines the imported target YODA::YODA.
include(HekitDependency)

hekit_config_tool(_YODA_compile COMMAND yoda-config --cppflags)
hekit_config_tool(_YODA_link COMMAND yoda-config --libs)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(YODA
  REQUIRED_VARS _YODA_link
  FAIL_MESSAGE "yoda-config not found or not working - YODA support is disabled")

if(YODA_FOUND)
  hekit_target_from_flags(YODA::YODA COMPILE "${_YODA_compile}" LINK "${_YODA_link}")
endif()
