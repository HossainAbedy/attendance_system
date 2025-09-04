<?php
// p1_dummy_testdb.php - Diagnostic version, tuned per your request
// - Hard-coded test DB: localhost / test_user / test_pass / test_end_db
// - Active INSERT -> att_raw_data_new
// - Alternative INSERT to att_raw_data (production) left commented out for later use
// - Prints JSON payload and exact SQL for each row
// - Uses directory lock to avoid concurrent Access DB use

error_reporting(E_ALL);
ini_set('display_errors', 1);

// ------------------------------
// TEST MySQL destination (required by user)
define('TEST_MYSQL_HOST','127.0.0.1');
define('TEST_MYSQL_USER','test_user');
define('TEST_MYSQL_PASS','test_pass');
define('TEST_MYSQL_DB','test_end_db');
define('TEST_MYSQL_PORT', 3306);

// Try to connect to test DB (mysqli)
$test_conn = @mysqli_connect(TEST_MYSQL_HOST, TEST_MYSQL_USER, TEST_MYSQL_PASS, TEST_MYSQL_DB, TEST_MYSQL_PORT);
if (!$test_conn) {
    $test_err = mysqli_connect_error();
    $test_connected = false;
} else {
    $test_connected = true;
    mysqli_set_charset($test_conn, 'utf8mb4');
}

// Path to ZKT Access DB - change if needed (user-provided path in this conversation)
$dbName_zk = "E:/ShareME/SBAC TAO/NewYear25/attendance-system/backend/att2000.mdb";

if (!file_exists($dbName_zk)) {
    die("Could not find ZKT DB file: $dbName_zk");
}

/**
 * LOCKING: directory-based lock to coordinate with other processes.
 * Uses atomic mkdir for acquisition; stale-lock removal supported.
 */
function acquire_lock_dir($lock_dir, $timeout = 15, $stale_seconds = 60) {
    $start = time();
    while (true) {
        $ok = @mkdir($lock_dir);
        if ($ok) {
            $stamp = $lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt";
            $pid = getmypid();
            @file_put_contents($stamp, "pid={$pid}\ncreated=" . date('c') . "\n");
            return true;
        }
        if (file_exists($lock_dir)) {
            $mtime = @filemtime($lock_dir);
            if ($mtime !== false && (time() - $mtime) > $stale_seconds) {
                @unlink($lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt");
                @rmdir($lock_dir);
                usleep(50000);
                continue;
            }
        }
        if ((time() - $start) >= $timeout) {
            return false;
        }
        usleep(200000); // 200ms
    }
}
function release_lock_dir($lock_dir) {
    @unlink($lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt");
    @rmdir($lock_dir);
}

// Decide lock dir next to MDB
$lock_dir = dirname($dbName_zk) . DIRECTORY_SEPARATOR . "access_lock";
$lock_timeout = 15;
$lock_stale = 60;

$got_lock = acquire_lock_dir($lock_dir, $lock_timeout, $lock_stale);
if (!$got_lock) {
    echo "Could not acquire Access DB lock (busy). Skipping this run.<br>";
    exit;
}

try {
    // Open Access DB via ODBC PDO
    try {
        $dsn2 = "odbc:Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=$dbName_zk;";
        $db_zk = new PDO($dsn2);
        $db_zk->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    } catch (PDOException $e) {
        release_lock_dir($lock_dir);
        die("Access DB connection failed: " . $e->getMessage());
    }

    // lookback window: last 1 day (you can change)
    $lDate = date('Y-m-d', strtotime("-1 day", strtotime(date("Y-m-d"))));

    // Query CHECKINOUT joining USERINFO using INNER JOIN (as you chose earlier)
    $sqlZK = "SELECT *
        FROM CHECKINOUT t1
        INNER JOIN USERINFO t2 ON t2.USERID = t1.USERID
        WHERE Format(CHECKTIME,'YYYY-MM-DD') > :lDate
        ORDER BY CHECKTIME
    ";
    $stmt2 = $db_zk->prepare($sqlZK);
    $stmt2->execute([':lDate' => $lDate]);

    // Output header
    echo "<h2>ZK -> Diagnostic (TEST DB configured)</h2>\n";
    if (!$test_connected) {
        echo "<div style='color:darkred; font-weight:bold;'>Test MySQL not connected: " . htmlspecialchars($test_err ?? 'unknown') . ". Inserts will be skipped but rows are displayed.</div>\n";
    } else {
        echo "<div style='color:green;'>Test MySQL connected. Rows will be attempted against test DB.</div>\n";
    }

    echo "<pre style='white-space:pre-wrap; word-break:break-word;'>\n";
    $counter = 0;

    // Helper: escape value and return a SQL-quoted string, using mysqli_real_escape_string when possible.
    if (!function_exists('escape_for_sql_and_quote')) {
        function escape_for_sql_and_quote($val) {
            global $test_conn;
            if ($val === null) return "NULL";
            $s = (string)$val;
            if (isset($test_conn) && $test_conn) {
                return "'" . mysqli_real_escape_string($test_conn, $s) . "'";
            } else {
                return "'" . addslashes($s) . "'";
            }
        }
    }

    while ($row = $stmt2->fetch(PDO::FETCH_ASSOC)) {
        $raw_checktime = $row["CHECKTIME"] ?? null;
        // Normalize date/time the same way existing scripts do:
        $logDate = date("Y-m-d", strtotime($raw_checktime));
        $logTime = date("H:i:s", strtotime("-10 minutes", strtotime($raw_checktime)));
        $userId  = isset($row['Badgenumber']) ? $row['Badgenumber'] : '';

        // Original behavior: skip if badge length > 4
        if (strlen($userId) > 4) continue;

        // Mark device so these rows are obviously from the FLASK side in the test DB
        $accessDevice = 'FLASK-ZKT-' . (isset($row['sn']) ? $row['sn'] : '');
        $accessDoor   = isset($row['sn']) ? $row['sn'] : '';

        // Build payload that would be inserted into att_raw_data*
        $payload = [
            'date' => $logDate,
            'time' => $logTime,
            'badge' => $userId,
            'door' => $accessDoor,
            'device' => $accessDevice,
            'source' => 'flask_php_zk_script'
        ];

        // Show JSON for clarity
        echo "ROW: " . json_encode($payload, JSON_UNESCAPED_SLASHES) . "\n";

        // Prepare escaped & quoted pieces
        $q_logDate = escape_for_sql_and_quote($logDate);
        $q_userId  = escape_for_sql_and_quote($userId);
        $q_logTime = escape_for_sql_and_quote($logTime);
        $q_accessDoor = escape_for_sql_and_quote($accessDoor);
        $q_accessDev  = escape_for_sql_and_quote($accessDevice);

        // ACTIVE INSERT -> write to att_raw_data_new (test table for FLASK data)
        $ins_sql_new = "INSERT INTO att_raw_data_new VALUES(NULL, $q_logDate, $q_userId, $q_userId, '', $q_logTime, '0', $q_accessDoor, '', $q_accessDev)";

        // ALTERNATIVE INSERT (commented out) -> real/production-like table att_raw_data
        // Uncomment when you want to write to the production-like table.
        // $ins_sql_prod = "INSERT INTO att_raw_data VALUES(NULL, $q_logDate, $q_userId, $q_userId, '', $q_logTime, '0', $q_accessDoor, '', $q_accessDev)";

        echo "SQL (new table): " . $ins_sql_new . "\n";
        // echo "SQL (prod table - commented): " . $ins_sql_prod . "\n";

        // Attempt test insert (no IGNORE so errors surface).
        if ($test_connected) {
            $res = @mysqli_query($test_conn, $ins_sql_new);
            if ($res === false) {
                $err = mysqli_error($test_conn);
                echo "TEST INSERT FAILED: " . htmlspecialchars($err) . "\n";
            } else {
                echo "TEST INSERT OK\n";
            }

            // If you want to run the production-like insert as well, uncomment below (but we leave it commented as requested)
            /*
            $res2 = @mysqli_query($test_conn, $ins_sql_prod);
            if ($res2 === false) {
                echo "PROD INSERT FAILED: " . htmlspecialchars(mysqli_error($test_conn)) . "\n";
            } else {
                echo "PROD INSERT OK\n";
            }
            */
        } else {
            echo "TEST DB not connected - skipping insert\n";
        }

        echo "----\n";
        $counter++;
    }

    echo "Fetched $counter rows shown (ZKT)\n";
    echo "</pre>\n";

    // Cleanup
    $db_zk = null;

} finally {
    // release lock and close test connection
    release_lock_dir($lock_dir);
    if (isset($test_conn) && $test_conn) {
        mysqli_close($test_conn);
    }
}
?>
