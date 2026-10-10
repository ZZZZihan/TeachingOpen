import java.io.FileOutputStream;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

/** Ordinary XLS using the same title/head row contract as JeecgController.importExcel. */
public final class NewsExcelFixture {
    public static void main(String[] args) throws Exception {
        {
            HSSFWorkbook workbook = new HSSFWorkbook();
            Sheet sheet = workbook.createSheet("资讯");
            sheet.createRow(0).createCell(0).setCellValue("资讯报表");
            sheet.createRow(1).createCell(0).setCellValue("测试导出人");
            Row head = sheet.createRow(2);
            head.createCell(0).setCellValue("标题"); head.createCell(1).setCellValue("内容"); head.createCell(2).setCellValue("状态");
            Row row = sheet.createRow(3);
            row.createCell(0).setCellValue(args[1]);
            row.createCell(1).setCellValue("<p><b>导入正文</b></p><img src='/fixture.png' onerror='window.newsXss=1'><svg onload='window.newsXss=2'></svg>");
            row.createCell(2).setCellValue(1);
            try (FileOutputStream output = new FileOutputStream(args[0])) { workbook.write(output); }
        }
    }
}
