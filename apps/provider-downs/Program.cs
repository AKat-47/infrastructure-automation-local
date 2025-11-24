using Google.Apis.Auth.OAuth2;
using Google.Apis.Services;
using Google.Apis.Sheets.v4;
using Google.Apis.Sheets.v4.Data;
using OpenQA.Selenium;
using OpenQA.Selenium.Chrome;
using OpenQA.Selenium.Support.UI;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

class Program
{
    private const string SpreadsheetId = "1wARq0np7YLN2RNM3kNDd0Y_b725OPUixJ1lUwTk-Kbg";
    private static SheetsService sheetsService;

    static void Main(string[] args)
    {
        var operators = new Dictionary<string, string>
        {
            { "МТС", "https://downdetector.su/mts" },
            { "Tele2", "https://downdetector.su/tele2" },
            { "Ростелеком", "https://downdetector.su/rostelekom" },
            { "Билайн", "https://downdetector.su/bilajn" },
            { "Мегафон", "https://downdetector.su/megafon" },
            { "Дом.ru", "https://downdetector.su/domru" }
        };

        var currentDateTime = DateTime.Now.ToString("yyyy-MM-dd HH:mm");

        // ---------- Настраиваем Selenium EdgeDriver ----------
        // Создаём уникальный каталог профиля в /tmp (или Path.GetTempPath())
        string profileDir = Path.Combine(Path.GetTempPath(), "edge-profile-" + Guid.NewGuid());
        Directory.CreateDirectory(profileDir);

        var chromeOpts = new ChromeOptions();
        chromeOpts.AddArgument("--headless");
        chromeOpts.AddArgument("--no-sandbox");
        chromeOpts.AddArgument("--disable-dev-shm-usage");
        chromeOpts.AddArgument($"--user-data-dir={profileDir}");


        var service = ChromeDriverService.CreateDefaultService();
        service.HideCommandPromptWindow = true;

        var collectedData = new Dictionary<string, List<object>>();

        using (var driver = new ChromeDriver(service, chromeOpts))
        {
            driver.Manage().Timeouts().PageLoad = TimeSpan.FromSeconds(45);

            foreach (var op in operators)
            {
                int day = 0, hour = 0;
                string regionsMerged = "", complaintsLevel = "Неизвестно";

                try
                {
                    driver.Navigate().GoToUrl(op.Value);
                    var wait = new WebDriverWait(driver, TimeSpan.FromSeconds(40));
                    var socialElem = wait.Until(e => e.FindElement(By.ClassName("social")));

                    int.TryParse(socialElem.FindElement(By.XPath(".//em[1]")).Text.Trim(), out hour);
                    int.TryParse(socialElem.FindElement(By.XPath(".//em[2]")).Text.Trim(), out day);

                    var complaintsText = socialElem.Text.Trim();
                    if (complaintsText.Contains("много")) complaintsLevel = "Много";
                    else if (complaintsText.Contains("умеренно")) complaintsLevel = "Умеренно";
                    else if (complaintsText.Contains("мало")) complaintsLevel = "Мало";

                    var regions = new List<string>();
                    try
                    {
                        var hist = driver.FindElement(By.CssSelector("div.histograms"));
                        var names = hist.FindElements(By.TagName("label"));
                        var perc = hist.FindElements(By.CssSelector("span.region"));
                        for (int i = 0; i < Math.Min(names.Count, perc.Count); i++)
                            regions.Add($"{names[i].Text.Trim()} {perc[i].Text.Trim()}");
                    }
                    catch (NoSuchElementException) { }

                    regionsMerged = string.Join("\n", regions);
                }
                catch (Exception ex)
                {
                    regionsMerged = $"Ошибка: {ex.Message}";
                }

                collectedData[$"{op.Key} - Жалобы за сутки"] = new List<object> { day };
                collectedData[$"{op.Key} - Жалобы за час"] = new List<object> { hour };
                collectedData[$"{op.Key} - Регионы"] = new List<object> { regionsMerged };
                collectedData[$"{op.Key} - Уровень жалоб"] = new List<object> { complaintsLevel };

                Thread.Sleep(1000);
            }

            driver.Quit();
        }

        // ---------- Работа с Google Sheets ----------
        var cred = GoogleCredential
            .FromFile("provider-falls-ea0c76990c0c.json")
            .CreateScoped(SheetsService.ScopeConstants.Spreadsheets);

        sheetsService = new SheetsService(new BaseClientService.Initializer
        {
            HttpClientInitializer = cred,
            ApplicationName = "Downdetector parser"
        });

        var getRequest = sheetsService.Spreadsheets.Values.Get(SpreadsheetId, "Sheet1");
        var response = getRequest.Execute();
        var existingValues = response.Values ?? new List<IList<object>>();

        if (existingValues.Count == 0)
        {
            // если пустая таблица — создаём шапку и первые строки
            var header = new List<object> { "Провайдер/Показатель", currentDateTime };
            var body = collectedData
                .Select(kvp => (IList<object>)new List<object> { kvp.Key, kvp.Value[0] })
                .ToList();

            var allData = new List<IList<object>> { header };
            allData.AddRange(body);

            var update = sheetsService.Spreadsheets.Values.Update(
                new ValueRange { Values = allData }, SpreadsheetId, "Sheet1");
            update.ValueInputOption = SpreadsheetsResource.ValuesResource.UpdateRequest.ValueInputOptionEnum.RAW;
            update.Execute();
        }
        else
        {
            // обновляем существующую таблицу
            existingValues[0].Add(currentDateTime);

            foreach (var kvp in collectedData)
            {
                var row = existingValues
                    .FirstOrDefault(r => r.Count > 0 && r[0].ToString() == kvp.Key);

                if (row != null)
                {
                    row.Add(kvp.Value[0]);
                }
                else
                {
                    // новая строка, заполняем пустыми до последнего столбца
                    var newRow = new List<object> { kvp.Key };
                    for (int i = 1; i < existingValues[0].Count - 1; i++)
                        newRow.Add("");
                    newRow.Add(kvp.Value[0]);
                    existingValues.Add(newRow);
                }
            }

            var update = sheetsService.Spreadsheets.Values.Update(
                new ValueRange { Values = existingValues }, SpreadsheetId, "Sheet1");
            update.ValueInputOption = SpreadsheetsResource.ValuesResource.UpdateRequest.ValueInputOptionEnum.RAW;
            update.Execute();
        }
    }
}

