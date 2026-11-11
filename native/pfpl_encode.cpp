// Include upstream unchanged serial source in its own translation unit.
// PFPL has no exported library API. main is renamed and never called.
#define main lfcb_unused_pfpl_compressor_main
#include "../third_party/PFPL/src/f32_abs_comp_cpu.cpp"
#undef main
extern "C" void lfcb_pfpl_encode(const unsigned char*in,int n,unsigned char*out,int*bytes,float eps){
 h_encode(in,n,out,*bytes,eps,std::numeric_limits<float>::infinity());
}
