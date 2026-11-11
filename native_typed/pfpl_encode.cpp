// Unmodified official PFPL ABS implementation; its CLI main is never invoked.
#include "adapter.hpp"
#include <limits>
#define main lfcb_unused_pfpl_compressor_main
#ifdef LFCB_DOUBLE
#include "../third_party/PFPL/src/f64_abs_comp_cpu.cpp"
#else
#include "../third_party/PFPL/src/f32_abs_comp_cpu.cpp"
#endif
#undef main
extern "C" void lfcb_pfpl_encode(const unsigned char*in,int n,unsigned char*out,int*bytes,double eps){
 h_encode(in,n,out,*bytes,Scalar(eps),std::numeric_limits<Scalar>::infinity());
}
