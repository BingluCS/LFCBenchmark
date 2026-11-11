#include "adapter.hpp"
#include <zfp.h>
#include <cstring>
const char*codec_name(){return "ZFP";}
Blob compress_api(const Scalar*data,Shape s,double eps){
 const auto type=sizeof(Scalar)==8?zfp_type_double:zfp_type_float;
 auto field=s.z==1?zfp_field_2d(const_cast<Scalar*>(data),type,s.x,s.y):zfp_field_3d(const_cast<Scalar*>(data),type,s.x,s.y,s.z);
 auto z=zfp_stream_open(nullptr);zfp_stream_set_execution(z,zfp_exec_serial);zfp_stream_set_accuracy(z,eps);
 size_t cap=zfp_stream_maximum_size(z,field);void*p=std::malloc(cap);require(p,"allocation failed");
 auto stream=stream_open(p,cap);zfp_stream_set_bit_stream(z,stream);zfp_stream_rewind(z);
 require(zfp_write_header(z,field,ZFP_HEADER_FULL)>0,"ZFP header failed");
 size_t bytes=zfp_compress(z,field);require(bytes>0,"ZFP compression failed");
 zfp_stream_close(z);stream_close(stream);zfp_field_free(field);return Blob(p,bytes);
}
Blob decompress_api(const Blob&b,Shape expected){
 auto z=zfp_stream_open(nullptr);zfp_stream_set_execution(z,zfp_exec_serial);
 auto stream=stream_open(b.data,b.bytes);zfp_stream_set_bit_stream(z,stream);zfp_stream_rewind(z);
 auto field=zfp_field_alloc();require(zfp_read_header(z,field,ZFP_HEADER_FULL)>0,"ZFP read header failed");
 require(zfp_field_size(field,nullptr)==expected.count()&&zfp_field_type(field)==(sizeof(Scalar)==8?zfp_type_double:zfp_type_float),"ZFP shape/dtype mismatch");
 Scalar*p=(Scalar*)std::malloc(expected.count()*sizeof(Scalar));require(p,"allocation failed");zfp_field_set_pointer(field,p);
 require(zfp_decompress(z,field)!=0,"ZFP decompression failed");
 zfp_stream_close(z);stream_close(stream);zfp_field_free(field);return Blob(p,expected.count()*sizeof(Scalar));
}
