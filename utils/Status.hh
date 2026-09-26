#pragma once

// ── Status.hh ────────────────────────────────────────────────────────────────
// Telling `hep` what is happening: JSON lines on fd 3, or plain lines on stderr (06 §3, 13 §2).
//
// The name is deliberate and slightly dangerous: X11's `Xlib.h` contains `#define Status int`, so any
// translation unit that includes an X11 header before this one would see our namespace turn into `int`
// with an error that points nowhere near the cause. The guard below turns that into one clear line.
// ROOT pulls in X11 on some platforms, which is exactly the situation the guard is for; `hep-run` does
// not link ROOT (09 §1), so this is a safety net rather than a daily problem.

#ifdef Status
#error "Status is a macro here: X11's Xlib.h defines `#define Status int`. Include Status.hh (or Core.hh) before any X11 or ROOT header, or #undef Status after them."
#endif

#include "Status/Types.hh"
#include "Status/Plain.hh"
#include "Status/Writer.hh"
#include "Status/Heartbeat.hh"
#include "Status/Timer.hh"
