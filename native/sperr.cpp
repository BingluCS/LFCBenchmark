#include "adapter.hpp"
#include <SPERR_C_API.h>
#include <algorithm>
const char*codec_name(){return "SPERR";}
Blob compress_api(const float*data,Shape s,double eps){
 void*p=nullptr;size_t bytes=0;
 int rc=C_API::sperr_comp_3d(data,1,s.x,s.y,s.z,std::min(s.x,size_t(256)),std::min(s.y,size_t(256)),std::min(s.z,size_t(256)),3,eps,1,&p,&bytes);
 require(rc==0,"SPERR compression failed");return Blob(p,bytes);
}
Blob decompress_api(const Blob&b,Shape expected){
 void*p=nullptr;size_t x=0,y=0,z=0;
 int rc=C_API::sperr_decomp_3d(b.data,b.bytes,1,1,&x,&y,&z,&p);
 require(rc==0&&x==expected.x&&y==expected.y&&z==expected.z,"SPERR decode/shape failed");return Blob(p,x*y*z*sizeof(float));
}
