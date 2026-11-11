#include "adapter.hpp"
#include <SPERR_C_API.h>
#include <algorithm>
const char*codec_name(){return "SPERR";}
Blob compress_api(const Scalar*data,Shape s,double eps){
 void*p=nullptr;size_t bytes=0;
 constexpr int is_float=sizeof(Scalar)==4;
 int rc;
 if(s.z==1) rc=C_API::sperr_comp_2d(data,is_float,s.x,s.y,3,eps,1,&p,&bytes);
 else rc=C_API::sperr_comp_3d(data,is_float,s.x,s.y,s.z,std::min(s.x,size_t(256)),std::min(s.y,size_t(256)),std::min(s.z,size_t(256)),3,eps,1,&p,&bytes);
 require(rc==0,"SPERR compression failed");return Blob(p,bytes);
}
Blob decompress_api(const Blob&b,Shape expected){
 void*p=nullptr;size_t x=0,y=0,z=0;int is_float=0;
 C_API::sperr_parse_header(b.data,&x,&y,&z,&is_float);
 require(x==expected.x&&y==expected.y&&z==expected.z&&is_float==(sizeof(Scalar)==4),"SPERR header mismatch");
 int rc;
 if(expected.z==1){
  require(b.bytes>10,"SPERR 2D stream too short");
  rc=C_API::sperr_decomp_2d((const unsigned char*)b.data+10,b.bytes-10,sizeof(Scalar)==4,x,y,&p);
 }else rc=C_API::sperr_decomp_3d(b.data,b.bytes,sizeof(Scalar)==4,1,&x,&y,&z,&p);
 require(rc==0,"SPERR decode failed");return Blob(p,x*y*z*sizeof(Scalar));
}
