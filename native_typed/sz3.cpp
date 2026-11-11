#include "adapter.hpp"
#include <SZ3/api/sz.hpp>
static void delbytes(void*p){delete[] (char*)p;}
static void delScalars(void*p){delete[] (Scalar*)p;}
const char*codec_name(){return "SZ3";}
Blob compress_api(const Scalar*data,Shape s,double eps){
 SZ3::Config c = s.z==1 ? SZ3::Config(s.y,s.x) : SZ3::Config(s.z,s.y,s.x);c.errorBoundMode=SZ3::EB_ABS;c.absErrorBound=eps;c.openmp=false;
 size_t bytes=0;auto p=SZ_compress(c,data,bytes);return Blob(p,bytes,delbytes);
}
Blob decompress_api(const Blob&b,Shape s){
 SZ3::Config c;Scalar*p=SZ_decompress<Scalar>(c,(const char*)b.data,b.bytes);
 require(c.num==s.count(),"SZ3 shape mismatch");return Blob(p,c.num*sizeof(Scalar),delScalars);
}
