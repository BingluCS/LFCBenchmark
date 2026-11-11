#define main lfcb_unused_pfpl_decompressor_main
#include "../third_party/PFPL/src/f32_abs_decomp_cpu.cpp"
#undef main
extern "C" void lfcb_pfpl_decode(const unsigned char*in,unsigned char*out,int*bytes){h_decode(in,out,*bytes);}
