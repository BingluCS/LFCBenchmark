#include "adapter.hpp"
#include <Falcons/api/falcons.hpp>
static void delbytes(void*p){delete[] (char*)p;}
static void delfloats(void*p){delete[] (float*)p;}
const char*codec_name(){return "Falcons";}
Blob compress_api(const float*data,Shape s,double eps){
 Falcons::Config c(s.z,s.y,s.x);c.errorBoundMode=Falcons::EB_ABS;c.absErrorBound=eps;c.openmp=false;
 size_t bytes=0;auto p=Falcons_compress(c,data,bytes);return Blob(p,bytes,delbytes);
}
Blob decompress_api(const Blob&b,Shape s){
 Falcons::Config c;float*p=Falcons_decompress<float>(c,(const char*)b.data,b.bytes);
 require(c.num==s.count(),"Falcons shape mismatch");return Blob(p,c.num*sizeof(float),delfloats);
}
