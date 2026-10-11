import java.io.FileInputStream;
import java.io.Closeable;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;

/** Read actual XLS/XLSX cells with the application's existing POI dependency. */
public final class ReadSpreadsheetCells {
    public static void main(String[] args) throws Exception {
        try (FileInputStream input = new FileInputStream(args[0])) {
            Workbook workbook = WorkbookFactory.create(input);
            try {
                for (int index = 0; index < workbook.getNumberOfSheets(); index++) {
                    Sheet sheet = workbook.getSheetAt(index);
                    for (Row row : sheet) {
                        for (Cell cell : row) {
                            System.out.println(Base64.getEncoder().encodeToString(
                                    cell.toString().getBytes(StandardCharsets.UTF_8)));
                        }
                    }
                }
            } finally {
                if (workbook instanceof Closeable) ((Closeable) workbook).close();
            }
        }
    }
}
