import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

/** Read actual exported XLS cells with the application's existing POI dependency. */
public final class ReadXlsCells {
    public static void main(String[] args) throws Exception {
        try (FileInputStream input = new FileInputStream(args[0])) {
            HSSFWorkbook workbook = new HSSFWorkbook(input);
            for (int index = 0; index < workbook.getNumberOfSheets(); index++) {
                Sheet sheet = workbook.getSheetAt(index);
                for (Row row : sheet) {
                    for (Cell cell : row) {
                        System.out.println(Base64.getEncoder().encodeToString(
                                cell.toString().getBytes(StandardCharsets.UTF_8)));
                    }
                }
            }
        }
    }
}
