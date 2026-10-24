// SPDX-License-Identifier: LGPL-2.1-or-later
// Force-included into GCS.cpp for the WebAssembly build only (build.sh: -include this file).
//
// PlaneGCS's diagnose() starts one of its two QR decompositions with std::async and waits for it.
// A wasm module without pthreads (the page is not cross-origin isolated) cannot start a thread, and
// libc++'s std::async then never returns. Here std::async in GCS.cpp becomes the deferred launch:
// the task runs in fut.wait(), after the other decomposition, which FreeCAD's comment there allows
// ("std::launch::async | std::launch::deferred policy"). The two do not share data, so the result
// is the same; tests/test_planegcs.py checks the wasm build against FreeCAD's answers.
#pragma once
#include <future>
#include <utility>

namespace std
{
template<class F, class... Args>
auto planegcs_deferred_async(F&& f, Args&&... args)
{
    return std::async(std::launch::deferred, std::forward<F>(f), std::forward<Args>(args)...);
}
}  // namespace std

#define async planegcs_deferred_async
