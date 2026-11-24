import test from 'node:test';
import assert from 'node:assert/strict';
import {File} from 'node:buffer';
import {prepareUpload} from '../public/image-upload.js';
const MIB=1024*1024;
function environment({sizes=[900000],width=8000,height=6000}={}){
 const previous={document:globalThis.document,createImageBitmap:globalThis.createImageBitmap,File:globalThis.File};let closed=false,calls=0;
 const canvas={width:0,height:0,getContext:()=>({fillStyle:'',fillRect(){},drawImage(){}}),toBlob(fn){fn(new Blob([new Uint8Array(sizes[Math.min(calls++,sizes.length-1)])],{type:'image/jpeg'}))}};
 globalThis.document={createElement:name=>{assert.equal(name,'canvas');return canvas}};globalThis.File=File;
 globalThis.createImageBitmap=async()=>({width,height,close(){closed=true}});
 return {canvas,get calls(){return calls},get closed(){return closed},restore(){for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value}}};
}
test('PDF original bytes and filename are retained while oversize PDFs get actionable errors',async()=>{
 const pdf=new File(['%PDF-test'],'invoice.pdf',{type:'application/pdf'});assert.equal(await prepareUpload(pdf),pdf);
 await assert.rejects(()=>prepareUpload(pdf,{maxBytes:2}),/PDF 超过/);
 await assert.rejects(()=>prepareUpload(pdf,{purpose:'payment-proof'}),/图片/);
});
test('large camera photo is scaled for readable invoice OCR and encoded beneath target',async()=>{
 const env=environment();try{
 const photo=new File([new Uint8Array(20*MIB)],'camera.JPG',{type:'image/jpeg'}),messages=[];
 const converted=await prepareUpload(photo,{maxBytes:30*MIB,onStatus:message=>messages.push(message)});
 assert.equal(converted.type,'image/jpeg');assert.equal(converted.name,'camera.jpg');assert.ok(converted.size<4*MIB);
 assert.equal(env.canvas.width,3600);assert.equal(env.canvas.height,2700);assert.equal(env.closed,true);assert.match(messages.join(' '),/优化/);
 }finally{env.restore()}
});
test('HEIC supported by browser converts to a JPEG accepted by the existing server',async()=>{
 const env=environment();try{
 const result=await prepareUpload(new File([new Uint8Array(200)],'photo.HEIC',{type:'image/heic'}),{purpose:'payment-proof'});
 assert.equal(result.type,'image/jpeg');assert.equal(result.name,'photo.jpg');assert.equal(env.canvas.width,2800);
 }finally{env.restore()}
});
test('compression retries at smaller dimensions and preserves QR legibility',async()=>{
 const env=environment({sizes:[6*MIB,3*MIB]});try{
 const result=await prepareUpload(new File([new Uint8Array(21*MIB)],'qr.png',{type:'image/png'}),{purpose:'alipay-qr'});
 assert.equal(result.size,3*MIB);assert.equal(env.calls,2);assert.equal(env.canvas.width,1920);assert.equal(env.closed,true);
 }finally{env.restore()}
});
test('small PNG screenshot is preserved without losing sharp text',async()=>{
 const photo=new File([new Uint8Array(1500)],'screenshot.png',{type:'image/png'});assert.equal(await prepareUpload(photo),photo);
});
