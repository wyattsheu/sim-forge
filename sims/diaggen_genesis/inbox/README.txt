把 PNG、JPG 或 JPEG 圖片放在這個資料夾即可。
背景排程每分鐘掃描一次；檔案連續兩次掃描保持穩定後才會收件，通常約 1–2 分鐘。
同內容圖片只建立一件任務；原圖保留在此，不會刪除或修改。
暫存上傳建議先用 .part 副檔名，完成後再改成 .png 或 .jpg。
不掃描子目錄；整個資料夾可使用 ./diaggen submit /path/to/folder --recursive。
狀態：在 sim-forge 根目錄執行 ./diaggen status。
輸出：sims/diaggen_genesis/runs/<run_id>/。
首次部署或服務停用後可執行 ./diaggen start；既有人工暫停旗標會保留。
