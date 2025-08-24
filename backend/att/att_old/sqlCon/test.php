<?php
$dbName_zk = "C:/Program Files (x86)/ZKTeco/att2000.mdb";

// Check if Access DB exists
if (!file_exists($dbName_zk)) {
    die("Could not find Access database file.");
}

// Connect to Access via ODBC
try {
    $db_zk = new PDO("odbc:Driver={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=$dbName_zk;");
    $db_zk->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    echo "Connected to Access OK.<br><br>";
} catch (PDOException $e) {
    die("Access connection failed: " . $e->getMessage());
}

// Include MySQL connection
include("database1.php");

// Check MySQL connection
if (!$mylink) {
    die("MySQL connection failed: " . mysqli_connect_error());
}

// Date filter
$lDate = date('Y-m-d', strtotime("-10 days"));

// Fetch logs from Access DB
$sql = "SELECT * FROM CHECKINOUT t1 
        LEFT JOIN USERINFO t2 ON t2.USERID = t1.USERID 
        WHERE Format(CHECKTIME,'YYYY-MM-DD') > ? 
        ORDER BY CHECKTIME";

try {
    $stmt_access = $db_zk->prepare($sql);
    $stmt_access->execute([$lDate]);
} catch (PDOException $e) {
    die("Access query failed: " . $e->getMessage());
}

$slZK = 0;

while ($row = $stmt_access->fetch(PDO::FETCH_ASSOC)) {
    $logDate = date("Y-m-d", strtotime($row["CHECKTIME"]));
    $logTime = date("H:i:s", strtotime("-10 minutes", strtotime($row['CHECKTIME'])));
    $userId = $row['Badgenumber'];

    if (strlen($userId) > 4) continue;

    $accessDevice = 'ZKT-' . $row['sn'];
    $accessDoor = $row['sn'];
    $slZK++;

    // Print original Access data
    echo "<strong>Access row #$slZK:</strong><br>";
    echo "<pre>";
    print_r($row);
    echo "</pre>";

    // Print transformed insert values
    echo "<strong>Transformed values:</strong><br>";
    echo "logDate = $logDate, logTime = $logTime, userId = $userId, accessDoor = $accessDoor, accessDevice = $accessDevice<br>";

    // Map to new MySQL table columns
    echo "<strong>Mapped to MySQL columns:</strong><br>";
    echo "att_date = $logDate, emp_id = $userId, device_emp_id_srl_raw_data = $userId, id_card_no = '', access_time = $logTime, accessBy = 0, access_door = $accessDoor, remarks = '', insertKey = $accessDevice<br><hr>";
}

echo "Fetched $slZK Record(s) from ZKT Devices.";
?>
