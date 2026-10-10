// forza - built-in CPU sampling profiler; see cpu_profile.cpp.

#pragma once

namespace forza::cpuprof {

void Start();  // "PROF:START" on the input FIFO
void Stop();   // "PROF:STOP": writes $FORZA_CPUPROF

}  // namespace forza::cpuprof
