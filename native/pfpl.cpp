#include "adapter.hpp"
#include <climits>
extern "C" void lfcb_pfpl_encode(const unsigned char*,int,unsigned char*,int*,float);
extern "C" void lfcb_pfpl_decode(const unsigned char*,unsigned char*,int*);
const char*codec_name(){return "PFPL";}
Blob compress_api(const float*data,Shape s,double eps){
 const size_t n=s.count()*sizeof(float);require(n<2147221529,"PFPL input exceeds upstream 32-bit size limit");
 const size_t chunks=(n+16383)/16384, cap=n+chunks*2+16384+16;
 auto p=(unsigned char*)std::malloc(cap);require(p,"allocation failed");int size=0;
 lfcb_pfpl_encode((const unsigned char*)data,int(n),p,&size,float(eps));
 require(size>0&&size_t(size)<=cap,"PFPL compressed size invalid");return Blob(p,size);
}
Blob decompress_api(const Blob&b,Shape s){
 const size_t n=s.count()*sizeof(float);auto p=(unsigned char*)std::malloc(n);require(p,"allocation failed");int size=0;
 lfcb_pfpl_decode((const unsigned char*)b.data,p,&size);require(size_t(size)==n,"PFPL decode size invalid");return Blob(p,n);
}
