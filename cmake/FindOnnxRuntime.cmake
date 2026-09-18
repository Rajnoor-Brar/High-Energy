# ONNX Runtime for `ML::OnnxModel` (13 §2), from $ONNXRUNTIME_DIR or $HEP_INSTALL/onnxruntime.
include(HekitDependency)

set(_ONNX_HINTS "$ENV{ONNXRUNTIME_DIR}" "$ENV{HEP_INSTALL}/onnxruntime")

find_path(OnnxRuntime_INCLUDE_DIR onnxruntime_cxx_api.h
          HINTS ${_ONNX_HINTS} PATH_SUFFIXES include include/onnxruntime)
find_library(OnnxRuntime_LIBRARY NAMES onnxruntime HINTS ${_ONNX_HINTS} PATH_SUFFIXES lib lib64)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(OnnxRuntime
  REQUIRED_VARS OnnxRuntime_INCLUDE_DIR OnnxRuntime_LIBRARY
  FAIL_MESSAGE "ONNX Runtime not found - ML inference is disabled")

if(OnnxRuntime_FOUND AND NOT TARGET OnnxRuntime::OnnxRuntime)
  add_library(OnnxRuntime::OnnxRuntime INTERFACE IMPORTED GLOBAL)
  target_include_directories(OnnxRuntime::OnnxRuntime SYSTEM INTERFACE ${OnnxRuntime_INCLUDE_DIR})
  target_link_libraries(OnnxRuntime::OnnxRuntime INTERFACE ${OnnxRuntime_LIBRARY})
  get_filename_component(_onnx_libdir ${OnnxRuntime_LIBRARY} DIRECTORY)
  target_link_options(OnnxRuntime::OnnxRuntime INTERFACE "LINKER:-rpath,${_onnx_libdir}")
endif()
