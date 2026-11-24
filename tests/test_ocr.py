"""Fictitious invoice layouts; no real guest documents are used."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ocr import extract_fields,_result,_paddle_document,recognize

BUYER='91510100MA6ABC1234'
SELLER='91511000MA6XYZ5678'

class InvoiceExtractionTests(unittest.TestCase):
    def test_explicit_fields_and_gross_total(self):
        fields=extract_fields('发票号码：26112000000000000001\n开票日期：2026年11月13日\n购买方名称：示例会务科技有限公司\n购买方税号：'+BUYER+'\n销售方名称：示例交通服务有限公司\n销售方税号：'+SELLER+'\n不含税金额：100.00\n税额合计：6.00\n价税合计（大写）壹佰零陆元整 （小写）￥106.00')
        self.assertEqual(fields['invoiceNumber'],'26112000000000000001')
        self.assertEqual(fields['date'],'2026-11-13')
        self.assertEqual(fields['buyerName'],'示例会务科技有限公司')
        self.assertEqual(fields['sellerName'],'示例交通服务有限公司')
        self.assertEqual(fields['buyerTaxId'],BUYER)
        self.assertEqual(fields['sellerTaxId'],SELLER)
        self.assertEqual((fields['amount'],fields['netAmount'],fields['taxAmount']),(106,100,6))

    def test_side_by_side_text_preserves_parties(self):
        text='购买方信息                 销售方信息\n名称：示例会务科技有限公司      名称：示例交通服务有限公司\n统一社会信用代码/纳税人识别号：'+BUYER+'      统一社会信用代码/纳税人识别号：'+SELLER+'\n合计 ￥100.00   ￥6.00\n价税合计（大写）壹佰零陆元整 （小写）￥106.00'
        fields=extract_fields(text)
        self.assertEqual(fields['buyerName'],'示例会务科技有限公司')
        self.assertEqual(fields['sellerName'],'示例交通服务有限公司')
        self.assertEqual(fields['buyerTaxId'],BUYER)
        self.assertEqual(fields['sellerTaxId'],SELLER)
        self.assertEqual((fields['amount'],fields['netAmount'],fields['taxAmount']),(106,100,6))

    def test_geometry_handles_interleaved_reading_order(self):
        # OCR may return the two columns out of order. Explicit headings set ownership.
        blocks=[]
        for x,prefix,name,tax in [(.04,'购买方信息','示例会务科技有限公司',BUYER),(.55,'销售方信息','示例交通服务有限公司',SELLER)]:
            for y,text in [(.22,prefix),(.28,'名称：'+name),(.34,'纳税人识别号：'+tax)]:
                blocks.append({'text':text,'x':x,'y':y,'height':.025,'width':.4,'page':0,'confidence':.99})
        blocks.append({'text':'项目名称','x':.1,'y':.43,'height':.025,'page':0})
        text='\n'.join(b['text'] for b in reversed(blocks))
        fields=extract_fields(text,blocks)
        self.assertEqual(fields['buyerName'],'示例会务科技有限公司')
        self.assertEqual(fields['sellerName'],'示例交通服务有限公司')
        self.assertEqual(fields['buyerTaxId'],BUYER)
        self.assertEqual(fields['sellerTaxId'],SELLER)

    def test_old_vertical_layout(self):
        fields=extract_fields('购买方\n名 称：示例会务科技有限公司\n纳 税 人 识 别 号：'+BUYER+'\n项目名称\n会议服务\n价税合计（小写）：106.00\n销售方\n名 称：示例交通服务有限公司\n纳税人识别号：'+SELLER)
        self.assertEqual(fields['buyerName'],'示例会务科技有限公司')
        self.assertEqual(fields['sellerName'],'示例交通服务有限公司')
        self.assertEqual(fields['buyerTaxId'],BUYER)
        self.assertEqual(fields['sellerTaxId'],SELLER)

    def test_combined_heading_box_does_not_override_text_ownership(self):
        blocks=[{'text':'购买方信息             销售方信息','x':.05,'y':.2,'height':.03},
                {'text':'名称：示例会务科技有限公司 名称：示例交通服务有限公司','x':.05,'y':.25,'height':.03},
                {'text':'税号：'+BUYER+' 税号：'+SELLER,'x':.05,'y':.3,'height':.03}]
        fields=extract_fields('\n'.join(b['text'] for b in blocks),blocks)
        self.assertEqual(fields['buyerTaxId'],BUYER)
        self.assertEqual(fields['sellerTaxId'],SELLER)
        self.assertEqual(fields['sellerName'],'示例交通服务有限公司')

    def test_tax_id_internal_letters_are_preserved(self):
        tax='91510100TIN1234567A'
        result=_result('购买方\n名称：示例有限公司\n纳税人识别号：'+tax+'\n价税合计：106.00')
        self.assertEqual(result['fields']['buyerTaxId'],tax)
        self.assertFalse(any('尚无法明确' in item for item in result['warnings']))

    def test_spaced_labels_full_width_and_zero_tax(self):
        fields=extract_fields('发 票 号 码：１２３４５６７８\n开 票 日 期：２０２６ 年 １ 月 ３ 日\n购买方税号：９１５１０１００ＭＡ６ＡＢＣ１２３４\n价 税 合 计（小 写）：￥１，２３４．５０\n税 额：０．００')
        self.assertEqual(fields['invoiceNumber'],'12345678')
        self.assertEqual(fields['buyerTaxId'],BUYER)
        self.assertEqual(fields['date'],'2026-01-03')
        self.assertEqual(fields['amount'],1234.5)
        self.assertEqual(fields['taxAmount'],0)
        self.assertIn('taxAmount',_result('税额：0.00')['recognizedFields'])

    def test_unknown_and_invalid_date_are_not_guessed(self):
        fields=extract_fields('会议活动\n纳税人识别号：'+SELLER+'\n开票日期：2026-02-31\n不含税金额：100.00\n税额：免税')
        self.assertEqual(fields['buyerTaxId'],'')
        self.assertEqual(fields['sellerTaxId'],'')
        self.assertEqual(fields['date'],'')
        self.assertEqual(fields['amount'],'')
        self.assertEqual(fields['taxAmount'],'')
        self.assertEqual(fields['netAmount'],100)
        self.assertEqual(extract_fields('nothing legible')['amount'],'')
        self.assertTrue(any('尚无法明确' in item for item in _result('纳税人识别号：'+SELLER)['warnings']))

    def test_warning_does_not_autocorrect_tax_id(self):
        result=_result('购买方税号：91510100MA6ABC12O4\n不含税金额：100.00\n税额：6.00\n价税合计：120.00')
        self.assertEqual(result['fields']['buyerTaxId'],'91510100MA6ABC12O4')
        self.assertTrue(any('O/I' in item for item in result['warnings']))
        self.assertTrue(any('不等于' in item for item in result['warnings']))

    def test_table_tax_heading_does_not_capture_net_amount_on_next_line(self):
        text='金额\n税率\n税额\n100.00\n6%\n6.00\n税额合计：6.00\n价税合计：106.00'
        self.assertEqual(extract_fields(text)['taxAmount'],6)
        self.assertEqual(extract_fields('税额\n100.00')['taxAmount'],'')
        self.assertEqual(extract_fields('税额：3.00\n税额合计：6.00')['taxAmount'],6)

    def test_split_party_cells_keep_values_inside_their_actual_columns(self):
        # Headings are left-aligned at each column edge. A midpoint between
        # their x coordinates would cut off the buyer's separately detected ID.
        boxes=[]
        for x,heading,name,tax in [(.03,'购买方信息','虚构会议服务有限公司',BUYER),(.53,'销售方信息','虚构酒店有限公司',SELLER)]:
            for text,dx,y,width in [(heading,0,.20,.03),('名称:',.05,.23,.06),(name,.13,.23,.29),
                                    ('纳税人识别号:',.05,.28,.17),(tax,.23,.28,.24)]:
                boxes.append(dict(text=text,x=x+dx,y=y,width=width,height=.025,page=0))
        boxes.append(dict(text='项目名称',x=.08,y=.36,height=.025))
        f=extract_fields('\n'.join(b['text'] for b in reversed(boxes)),boxes)
        self.assertEqual((f['buyerName'],f['sellerName']),('虚构会议服务有限公司','虚构酒店有限公司'))
        self.assertEqual((f['buyerTaxId'],f['sellerTaxId']),(BUYER,SELLER))

    def test_multiline_vertical_party_headings_and_split_name_values(self):
        boxes=[]
        for x,heading,name,tax in [(.02,'购\n买\n方\n信\n息','虚构购方有限公司',BUYER),(.52,'销\n售\n方\n信\n息','虚构销方有限公司',SELLER)]:
            for text,dx,y,width,height in [(heading,0,.20,.03,.12),('名称:',.06,.22,.06,.02),
                                         (name,.06,.25,.27,.02),('统一社会信用代码:',.06,.29,.18,.02),
                                         (tax,.24,.29,.23,.02)]:
                boxes.append(dict(text=text,x=x+dx,y=y,width=width,height=height,page=0))
        boxes.append(dict(text='货物或应税劳务、服务名称',x=.08,y=.39,height=.025))
        f=extract_fields('\n'.join(b['text'] for b in boxes),boxes)
        self.assertEqual((f['buyerName'],f['sellerName']),('虚构购方有限公司','虚构销方有限公司'))
        self.assertEqual((f['buyerTaxId'],f['sellerTaxId']),(BUYER,SELLER))

    def test_missing_vertical_seller_title_uses_two_labelled_vat_columns(self):
        boxes=[dict(text='电子发',x=.35,y=.05,width=.14,height=.04),
               dict(text='票(普通发票)',x=.50,y=.05,width=.22,height=.04),
               dict(text='购买方信息',x=.02,y=.20,width=.025,height=.12)]
        for x,name,tax in [(.06,'虚构会务科技有限公司',BUYER),(.56,'虚构交通服务有限公司',SELLER)]:
            boxes.extend([dict(text='名称:'+name,x=x,y=.23,width=.36,height=.03),
                          dict(text='统一社会信用代码/纳税人识别号:'+tax,x=x,y=.30,width=.42,height=.03)])
        boxes.append(dict(text='项目名称',x=.07,y=.38,height=.025))
        f=extract_fields('\n'.join(b['text'] for b in boxes),boxes)
        self.assertEqual((f['buyerName'],f['sellerName']),('虚构会务科技有限公司','虚构交通服务有限公司'))
        self.assertEqual((f['buyerTaxId'],f['sellerTaxId']),(BUYER,SELLER))
        # Without the VAT context and aligned second labelled column, remain conservative.
        boxes[0]['text']='普通会议资料'
        f=extract_fields('\n'.join(b['text'] for b in boxes),boxes)
        self.assertEqual(f['sellerTaxId'],'')

    def test_totals_row_is_read_from_separate_and_slightly_misaligned_boxes(self):
        boxes=[dict(text=t,x=x,y=y,width=w,height=.025,page=0) for t,x,y,w in [
            ('税额',.87,.35,.05),('3.00',.87,.40,.08),('合计',.10,.60,.06),
            ('¥100.00',.65,.60,.12),('¥6.00',.88,.612,.08),('价税合计(小写)',.44,.69,.16),('¥106.00',.66,.69,.12)]]
        f=extract_fields('\n'.join(b['text'] for b in reversed(boxes)),boxes)
        self.assertEqual((f['netAmount'],f['taxAmount'],f['amount']),(100,6,106))

    def test_unrelated_or_ambiguous_totals_cells_are_not_paired(self):
        for extra in [dict(text='¥6.00',x=.9,y=.80,width=.06,height=.025,page=0),
                      dict(text='¥6.00',x=.9,y=.60,width=.06,height=.025,page=1)]:
            boxes=[dict(text='合计',x=.1,y=.6,height=.025,page=0),dict(text='¥100.00',x=.6,y=.6,height=.025,page=0),extra]
            f=extract_fields('\n'.join(b['text'] for b in boxes),boxes)
            self.assertEqual((f['netAmount'],f['taxAmount']),('',''))

    def test_ocr_label_omissions_preserve_ids_and_validate_the_printed_net(self):
        text='购买方信息\n名称:虚构会务有限公司\n纳税识别号:'+BUYER+'\n销售方信息\n名称:虚构酒店有限公司\n纳税识别号:'+SELLER+'\n合计额:¥100.00\n税额合计:¥6.00\n价税合计(小写):¥106.00'
        f=extract_fields(text)
        self.assertEqual((f['buyerTaxId'],f['sellerTaxId']),(BUYER,SELLER))
        self.assertEqual((f['sellerName'],f['netAmount'],f['taxAmount']),('虚构酒店有限公司',100,6))
        self.assertEqual(extract_fields(text.replace('¥100.00','¥999.00'))['netAmount'],'')

    def test_partial_pdf_extraction_is_supplemented_without_overwriting_native_values(self):
        fake_reader=SimpleNamespace(is_encrypted=False,pages=[object()])
        native_text='电子发票(普通发票)\n发票号码:12345678901234567890\n购买方名称:虚构购方有限公司\n价税合计:106.00'
        ocr_text='电子发票(普通发票)\n购买方名称:有误购方有限公司\n销售方名称:虚构销方有限公司\n销售方税号:'+SELLER+'\n不含税金额:100.00\n税额合计:6.00\n价税合计:999.00'
        with patch('pypdf.PdfReader',return_value=fake_reader),patch('ocr._pdf_document',return_value=(native_text,[])),\
             patch('ocr.capabilities',return_value={'imageAvailable':True,'imageEngine':'PaddleOCR','engine':'PaddleOCR'}),\
             patch('ocr._paddle_document',return_value=(ocr_text,[])) as raster:
            r=recognize(Path('synthetic-mixed.pdf'),'application/pdf')
        self.assertEqual(raster.call_count,1)
        self.assertEqual(r['fields']['buyerName'],'虚构购方有限公司')
        self.assertEqual(r['fields']['amount'],106)
        self.assertEqual((r['fields']['sellerName'],r['fields']['sellerTaxId'],r['fields']['netAmount'],r['fields']['taxAmount']),
                         ('虚构销方有限公司',SELLER,100,6))

    def test_failed_pdf_supplement_preserves_the_successful_native_fields(self):
        fake_reader=SimpleNamespace(is_encrypted=False,pages=[object()])
        native_text='电子发票(普通发票)\n价税合计:106.00'
        with patch('pypdf.PdfReader',return_value=fake_reader),patch('ocr._pdf_document',return_value=(native_text,[])),\
             patch('ocr.capabilities',return_value={'imageAvailable':True,'imageEngine':'Apple Vision','engine':'Apple Vision'}),\
             patch('ocr._vision_document',side_effect=RuntimeError('synthetic failure')):
            r=recognize(Path('synthetic-mixed.pdf'),'application/pdf')
        self.assertEqual((r['status'],r['fields']['amount']),('done',106))

    def test_scanned_pdf_limits_pages_and_cleans_private_copy_on_error(self):
        from pypdf import PdfReader,PdfWriter
        class FailingEngine:
            def predict(self,input):
                self.source=Path(input)
                self.pages=len(PdfReader(input).pages)
                raise RuntimeError('synthetic inference failure')
        fake=FailingEngine()
        work=ROOT.parents[1]/'work';work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ocr-tests-',dir=work) as tmp:
            source=Path(tmp)/'extensionless-private-file'
            writer=PdfWriter()
            for _ in range(6): writer.add_blank_page(width=200,height=200)
            with source.open('wb') as handle: writer.write(handle)
            with patch.dict(sys.modules,{'paddleocr':SimpleNamespace(PaddleOCR=lambda **kw:fake)}),patch('ocr._ENGINE',fake):
                with self.assertRaises(RuntimeError): _paddle_document(source,'application/pdf')
            self.assertEqual(fake.pages,5)
            self.assertFalse(fake.source.exists())
            self.assertFalse(fake.source.parent.exists())
            self.assertTrue(source.exists())

if __name__=='__main__': unittest.main()
