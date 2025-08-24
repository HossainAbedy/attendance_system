<?php
// test_p1.php - debug/test script for Access -> MySQL import
// Place in web root and browse to it. By default it will NOT insert.
// To actually run inserts add ?run=1 to the URL.

ini_set('display_errors', 1);
error_reporting(E_ALL);

echo "<h2>Access -> MySQL Import Tester</h2>";

$doRun = (isset($_GET['run']) && $_GET['run']=='1') ? true : false;
echo "<p>Mode: <strong>" . ($doRun ? "RUN (will attempt inserts)" : "TEST only (no inserts)") . "</strong></p>";

// Access DB path (adjust if needed)
$dbName_zk = "D:/ABEDY/attendance-system/backend/att2000.mdb";
if (!file_exists($dbName_zk)) {
    die("<b>Fatal:</b> Access DB file not found at <code>$dbName_zk</code>");
}

// Connect to Access (PDO ODBC)
try {
    $db_zk = new PDO("odbc:Driver={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=$dbName_zk;");
    $db_zk->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    echo "<p>Connected to Access DB OK.</p>";
} catch (PDOException $e) {
    die("<b>Access connection failed:</b> " . htmlspecialchars($e->getMessage()));
}

// Include MySQL connection (your existing include must set $mylink as mysqli connection)
include("database1.php");
if (!isset($mylink) || !$mylink) {
    die("<b>Fatal:</b> MySQL connection variable <code>\$mylink</code> not present or invalid. Check database1.php");
}

// Which MySQL table we insert into
$table = 'att_raw_data';

// Get MySQL table columns
$cols = [];
$res = mysqli_query($mylink, "SHOW COLUMNS FROM `{$table}`");
if (!$res) {
    die("<b>Fatal:</b> Could not read table structure: " . htmlspecialchars(mysqli_error($mylink)));
}
while ($r = mysqli_fetch_assoc($res)) {
    $cols[] = $r['Field'];
}
mysqli_free_result($res);

echo "<h3>MySQL table <code>{$table}</code> columns</h3>";
echo "<pre>" . htmlspecialchars(implode(", ", $cols)) . "</pre>";

// Define the columns your current INSERT expects (matching your script)
$expectedCols = ['id','log_date','user_id','badgenumber','something','log_time','status','access_door','something2','access_device'];

// Check for missing expected columns
$missing = array_diff($expectedCols, $cols);
if (!empty($missing)) {
    echo "<p style='color:darkred'><strong>Warning:</strong> These expected columns are <u>missing</u> in MySQL table <code>{$table}</code>:</p>";
    echo "<pre>" . htmlspecialchars(implode(", ", $missing)) . "</pre>";
    echo "<p>You can either modify the PHP to match real columns or add these columns to MySQL.</p>";
} else {
    echo "<p style='color:green'><strong>All expected columns are present in MySQL table.</strong></p>";
}

// Date filter (same as your script)
$lDate = date('Y-m-d', strtotime("-10 days"));
echo "<p>Fetching Access rows WHERE Format(CHECKTIME,'YYYY-MM-DD') > <strong>$lDate</strong></p>";

// Prepare Access query
$sql = "SELECT * FROM CHECKINOUT t1
        LEFT JOIN USERINFO t2 ON t2.USERID = t1.USERID
        WHERE Format(CHECKTIME,'YYYY-MM-DD') > ?
        ORDER BY CHECKTIME";

try {
    $stmt_access = $db_zk->prepare($sql);
    $stmt_access->execute([$lDate]);
} catch (PDOException $e) {
    die("<b>Access query failed:</b> " . htmlspecialchars($e->getMessage()));
}

// Prepare the insert SQL exactly as your script uses (including id=NULL)
$insert_sql = "INSERT INTO `{$table}` 
    (id, log_date, user_id, badgenumber, something, log_time, status, access_door, something2, access_device)
    VALUES (NULL, ?, ?, ?, '', ?, 0, ?, '', ?)";
echo "<h3>Prepared INSERT SQL (placeholders)</h3>";
echo "<pre>" . htmlspecialchars($insert_sql) . "</pre>";

// If doRun, prepare a mysqli statement once
$insert_stmt = null;
if ($doRun && empty($missing)) {
    $insert_stmt = mysqli_prepare($mylink, $insert_sql);
    if (!$insert_stmt) {
        die("<b>Fatal:</b> Could not prepare MySQL insert statement: " . htmlspecialchars(mysqli_error($mylink)));
    } else {
        echo "<p style='color:green'>MySQL prepared statement created successfully.</p>";
    }
} elseif ($doRun && !empty($missing)) {
    echo "<p style='color:red'><strong>Run blocked:</strong> missing columns prevent inserts. Add columns or switch to TEST mode.</p>";
    $doRun = false;
}

// Iterate Access rows and show comparison
echo "<h3>Rows preview (first 200 rows shown) — shows Access source, transformed values, and insert params</h3>";
echo "<pre>";
$counter = 0;
while (($row = $stmt_access->fetch(PDO::FETCH_ASSOC)) && $counter < 200) {
    $counter++;
    // Raw Access values
    $raw = $row;
    // Derived values
    $logDate = isset($row['CHECKTIME']) ? date("Y-m-d", strtotime($row["CHECKTIME"])) : '';
    $logTime = isset($row['CHECKTIME']) ? date("H:i:s", strtotime("-10 minutes", strtotime($row['CHECKTIME']))) : '';
    $userId  = isset($row['Badgenumber']) ? $row['Badgenumber'] : '';
    $accessDevice = 'ZKT-' . (isset($row['sn'])?$row['sn']:'');
    $accessDoor   = isset($row['sn']) ? $row['sn'] : '';

    echo "=== Row #{$counter} ===\n";
    echo "Raw Access fields:\n";
    foreach ($raw as $k => $v) {
        echo "  [$k] => " . (is_null($v) ? 'NULL' : $v) . "\n";
    }

    echo "\nTransformed values:\n";
    echo "  logDate   = " . $logDate . "\n";
    echo "  logTime   = " . $logTime . "\n";
    echo "  userId    = " . $userId . "\n";
    echo "  accessDoor= " . $accessDoor . "\n";
    echo "  accessDev = " . $accessDevice . "\n";

    // Show parameters array that will be bound in insert (matching your script order)
    $params = [$logDate, $userId, $userId, $logTime, $accessDoor, $accessDevice];
    echo "\nInsert parameters (in order):\n";
    foreach ($params as $i => $p) {
        echo "  param[".($i+1)."] = " . (is_null($p) ? 'NULL' : $p) . "\n";
    }

    // Optional: quick validation before insert
    $bad = [];
    if ($userId === '' || strlen($userId) > 4) {
        $bad[] = "userId empty or too long (>4)";
    }
    if ($logDate === '') $bad[] = "logDate empty";
    if ($logTime === '') $bad[] = "logTime empty";

    if (!empty($bad)) {
        echo "\nValidation problems: " . implode("; ", $bad) . "\n";
        echo "Will NOT insert this row.\n";
    } else {
        // If running and prepared, execute
        if ($doRun && $insert_stmt) {
            mysqli_stmt_bind_param($insert_stmt, "ssssss", $params[0], $params[1], $params[2], $params[3], $params[4], $params[5]);
            $ok = mysqli_stmt_execute($insert_stmt);
            if ($ok) {
                echo "\nINSERT: OK\n";
            } else {
                echo "\nINSERT: FAILED => " . mysqli_stmt_error($insert_stmt) . "\n";
            }
        } else {
            echo "\nRUN MODE is TEST only - not inserting.\n";
        }
    }

    echo str_repeat("-",40) . "\n\n";
}
echo "</pre>";

if ($doRun && $insert_stmt) {
    mysqli_stmt_close($insert_stmt);
}

// Summary
echo "<p>Rows processed (previewed): {$counter}.</p>";
if (!$doRun) {
    echo "<p style='color:blue'>No rows were inserted (you ran in TEST mode). To actually insert, reload with <code>?run=1</code>.</p>";
}
