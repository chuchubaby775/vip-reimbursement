/** Optimize camera photos locally before upload; PDFs retain their original bytes. */
const MIB=1024*1024;
const IMAGE_EXT=/\.(jpe?g|png|webp|heic|heif|avif|gif|bmp)$/i;
const HEIC_EXT=/\.(heic|heif)$/i;
function fileType(file){
 const type=(file.type||'').toLowerCase();
 if(type)return type;
 if(/\.pdf$/i.test(file.name))return 'application/pdf';
 if(/\.jpe?g$/i.test(file.name))return 'image/jpeg';
 if(/\.png$/i.test(file.name))return 'image/png';
 return '';
}
async function decode(file){
 if(typeof createImageBitmap==='function'){
  try{const bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});return {image:bitmap,width:bitmap.width,height:bitmap.height,close:()=>bitmap.close()}}catch{}
 }
 return new Promise((resolve,reject)=>{
  const url=URL.createObjectURL(file),image=new Image();
  image.onload=()=>{URL.revokeObjectURL(url);resolve({image,width:image.naturalWidth,height:image.naturalHeight,close(){}})};
  image.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('图片无法解码'))};image.src=url;
 });
}
function jpeg(canvas,quality){return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('图片处理失败，请换一张清晰截图')),'image/jpeg',quality))}
export async function prepareUpload(file,{maxBytes=30*MIB,purpose='invoice',onStatus=()=>{}}={}){
 if(!file?.size)throw new Error('文件为空，请重新选择');
 const type=fileType(file);
 if(type==='application/pdf'){
  if(purpose==='payment-proof'||purpose==='alipay-qr')throw new Error('请上传支付记录或收款码图片');
  if(file.size>maxBytes)throw new Error(`PDF 超过 ${Math.round(maxBytes/MIB)} MB，请导出体积较小的原始电子发票`);
  return file.type===type?file:new File([file],file.name,{type,lastModified:file.lastModified});
 }
 if(!type.startsWith('image/')&&!IMAGE_EXT.test(file.name))throw new Error('请上传 PDF、JPG、PNG 或手机照片');
 if(file.size>80*MIB)throw new Error('照片超过 80 MB，请裁掉多余背景或选择清晰截图后上传');
 // Ordinary small JPG/PNG files need no re-encoding, preserving all fine text.
 if(['image/jpeg','image/png'].includes(type)&&file.size<=Math.min(2*MIB,maxBytes))return file.type===type?file:new File([file],file.name,{type,lastModified:file.lastModified});
 onStatus('正在优化照片大小，请保持页面打开…');
 let decoded;
 try{decoded=await decode(file)}catch{
  throw new Error(HEIC_EXT.test(file.name)||/heic|heif/.test(type)?'此浏览器暂不支持这张 HEIC 照片，请在相册分享为 JPG，或截屏后上传；已填内容已保留':'图片无法读取，请选择 JPG、PNG 或清晰截图');
 }
 try{
  if(!decoded.width||!decoded.height)throw new Error('图片尺寸无效，请重新选择');
  const maxSide=purpose==='invoice'?3600:purpose==='alipay-qr'?2400:2800;
  let scale=Math.min(1,maxSide/Math.max(decoded.width,decoded.height));
  const target=Math.min(4*MIB,maxBytes),canvas=document.createElement('canvas');
  const context=canvas.getContext('2d',{alpha:false});if(!context)throw new Error('浏览器无法处理图片，请使用清晰截图');
  let output;
  for(let attempt=0;attempt<5;attempt++){
   canvas.width=Math.max(1,Math.round(decoded.width*scale));canvas.height=Math.max(1,Math.round(decoded.height*scale));
   context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(decoded.image,0,0,canvas.width,canvas.height);
   output=await jpeg(canvas,attempt===0?.92:.84);
   if(output.size<=target)break;
   scale*=.8;
  }
  if(!output||output.size>maxBytes)throw new Error('图片仍过大，请裁去票据以外的背景后重试');
  if(['image/jpeg','image/png'].includes(type)&&file.size<=maxBytes&&output.size>=file.size)return file;
  const name=file.name.replace(/\.[^.]+$/,'')+'.jpg';
  onStatus(`照片已优化至 ${(output.size/MIB).toFixed(1)} MB，正在上传…`);
  return new File([output],name,{type:'image/jpeg',lastModified:file.lastModified});
 }finally{decoded.close()}
}
